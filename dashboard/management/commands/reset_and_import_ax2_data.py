import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from dashboard.models import EvaluationCriterion, EvaluationRound, EvaluationTemplate


PERSONAL_HEADERS = [
    "평가자 별칭",
    "소속 팀",
    "평가 대상 팀원 별칭",
    "역할 수행 및 책임감",
    "프로젝트 기여도",
    "일정 및 약속 준수",
    "의사소통 및 협업",
    "문제 해결 및 적극성",
]

TEAM_HEADERS = [
    "평가자 별칭",
    "평가자 소속 팀",
    "평가 대상 팀",
    "문제 정의 및 목표의 명확성",
    "요구사항 충족 및 기능 완성도",
    "기술적 설계 및 구현 완성도",
    "AI/AX 활용의 적절성",
    "발표 및 질의응답",
]

PERSONAL_CRITERIA = PERSONAL_HEADERS[3:]
TEAM_CRITERIA = TEAM_HEADERS[3:]

RAW_TABLE = "dashboard_officialevaluationresponse"


class Command(BaseCommand):
    help = (
        "기존 dashboard 업무 데이터를 모두 초기화하되 staff/superuser 계정은 보존하고, "
        "AX2 공식 개인/팀 평가 CSV를 원본 그대로 적재한 뒤 지정 평가 템플릿을 생성합니다. "
        "기본 실행은 dry-run이며 실제 반영에는 --apply가 필요합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument("personal_csv", help="AX2 개인동료평가 CSV 경로")
        parser.add_argument("team_csv", help="AX2 팀평가 CSV 경로")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="실제로 초기화와 import를 수행합니다. 생략하면 dry-run만 수행합니다.",
        )
        parser.add_argument(
            "--round-name",
            default="AX2 2차 프로젝트",
            help="공식 데이터를 보관할 회차 이름",
        )

    def handle(self, *args, **options):
        personal = self._load_csv(options["personal_csv"], PERSONAL_HEADERS, "personal")
        team = self._load_csv(options["team_csv"], TEAM_HEADERS, "team")

        self._print_preview(personal, team, apply=options["apply"])

        if not options["apply"]:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("DRY-RUN 완료: DB는 변경하지 않았습니다."))
            self.stdout.write(
                "실제 반영하려면 같은 명령 끝에 --apply 를 붙여 다시 실행하세요."
            )
            return

        if connection.vendor != "postgresql":
            raise CommandError(
                "실제 초기화는 PostgreSQL에서만 허용합니다. "
                f"현재 DB backend: {connection.vendor}"
            )

        self._assert_raw_table_exists()

        with transaction.atomic():
            preserved_admins = list(
                User.objects.filter(Q(is_staff=True) | Q(is_superuser=True))
                .values_list("username", flat=True)
                .order_by("username")
            )

            self._truncate_dashboard_data()

            deleted_users, _ = User.objects.exclude(
                Q(is_staff=True) | Q(is_superuser=True)
            ).delete()

            evaluation_round = self._create_round(options["round_name"])
            self._create_official_templates()
            self._insert_raw_rows(evaluation_round.id, personal)
            self._insert_raw_rows(evaluation_round.id, team)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("AX2 공식 데이터 초기화/import 완료"))
        self.stdout.write(f"보존 관리자: {', '.join(preserved_admins) or '(없음)'}")
        self.stdout.write(f"삭제된 비관리자 관련 객체 수: {deleted_users}")
        self.stdout.write(f"개인 원본 응답: {len(personal['rows'])}건")
        self.stdout.write(f"팀 원본 응답: {len(team['rows'])}건")
        self.stdout.write(f"총 원본 응답: {len(personal['rows']) + len(team['rows'])}건")
        self.stdout.write("공식 템플릿: 개인 5문항 / 팀 5문항")
        self.stdout.write(
            self.style.WARNING(
                "중복 응답, 빈 점수, 팀 표기 충돌은 원본 자료이므로 수정/삭제/보정하지 않았습니다."
            )
        )

    def _load_csv(self, filename, expected_headers, response_type):
        path = Path(filename).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise CommandError(f"CSV 파일을 찾을 수 없습니다: {path}")

        raw_bytes = path.read_bytes()
        sha256 = hashlib.sha256(raw_bytes).hexdigest()

        with path.open("r", encoding="utf-8-sig", newline="") as fp:
            reader = csv.DictReader(fp)
            headers = list(reader.fieldnames or [])
            if headers != expected_headers:
                raise CommandError(
                    f"{path.name} 헤더가 지정 양식과 다릅니다.\n"
                    f"기대: {expected_headers}\n"
                    f"실제: {headers}"
                )

            rows = []
            for source_row, row in enumerate(reader, start=2):
                if None in row:
                    raise CommandError(
                        f"{path.name} {source_row}행의 열 개수가 헤더와 맞지 않습니다."
                    )
                payload = {
                    header: "" if row.get(header) is None else row.get(header)
                    for header in expected_headers
                }
                rows.append({"source_row": source_row, "payload": payload})

        if not rows:
            raise CommandError(f"{path.name}에 평가 응답이 없습니다.")

        return {
            "type": response_type,
            "path": path,
            "filename": path.name,
            "sha256": sha256,
            "headers": expected_headers,
            "rows": rows,
        }

    def _print_preview(self, personal, team, *, apply):
        admin_count = User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).count()
        non_admin_count = User.objects.exclude(Q(is_staff=True) | Q(is_superuser=True)).count()
        dashboard_tables = self._dashboard_tables()

        personal_duplicate_groups = self._duplicate_groups(
            personal["rows"],
            ("평가자 별칭", "소속 팀", "평가 대상 팀원 별칭"),
        )
        team_duplicate_groups = self._duplicate_groups(
            team["rows"],
            ("평가자 별칭", "평가자 소속 팀", "평가 대상 팀"),
        )
        personal_blank_scores = self._blank_score_rows(personal["rows"], PERSONAL_CRITERIA)
        team_blank_scores = self._blank_score_rows(team["rows"], TEAM_CRITERIA)
        team_conflicts = self._alias_team_conflicts(personal["rows"], team["rows"])

        mode = "실제 반영" if apply else "DRY-RUN"
        self.stdout.write(self.style.MIGRATE_HEADING(f"AX2 공식 데이터 import 미리보기 ({mode})"))
        self.stdout.write(f"개인 CSV: {personal['filename']} / {len(personal['rows'])}건")
        self.stdout.write(f"  SHA256: {personal['sha256']}")
        self.stdout.write(f"팀 CSV: {team['filename']} / {len(team['rows'])}건")
        self.stdout.write(f"  SHA256: {team['sha256']}")
        self.stdout.write(f"총 원본 응답: {len(personal['rows']) + len(team['rows'])}건")
        self.stdout.write("")
        self.stdout.write(f"보존할 admin/staff 계정: {admin_count}개")
        self.stdout.write(f"삭제할 비관리자 계정: {non_admin_count}개")
        self.stdout.write(f"초기화할 dashboard_* 테이블: {len(dashboard_tables)}개")
        self.stdout.write("기존 평가 템플릿/문항도 전부 초기화됩니다.")
        self.stdout.write("")
        self.stdout.write(
            f"원본 중복 그룹: 개인 {len(personal_duplicate_groups)}개 / "
            f"팀 {len(team_duplicate_groups)}개 (그대로 보존)"
        )
        self.stdout.write(
            f"빈 점수 포함 행: 개인 {len(personal_blank_scores)}개 / "
            f"팀 {len(team_blank_scores)}개 (그대로 보존)"
        )
        self.stdout.write(
            f"동일 별칭의 복수 팀 표기: {len(team_conflicts)}명 (그대로 보존)"
        )

        if personal_duplicate_groups:
            self.stdout.write("개인 중복 예시:")
            for key, count in personal_duplicate_groups[:5]:
                self.stdout.write(f"  - {key} : {count}건")
        if team_duplicate_groups:
            self.stdout.write("팀 중복 예시:")
            for key, count in team_duplicate_groups[:5]:
                self.stdout.write(f"  - {key} : {count}건")
        if team_conflicts:
            self.stdout.write("팀 표기 충돌 예시:")
            for alias, teams in team_conflicts[:5]:
                self.stdout.write(f"  - {alias}: {', '.join(teams)}")

    @staticmethod
    def _duplicate_groups(rows, keys):
        counter = Counter(
            tuple(item["payload"].get(key, "") for key in keys)
            for item in rows
        )
        return [(key, count) for key, count in counter.items() if count > 1]

    @staticmethod
    def _blank_score_rows(rows, score_headers):
        return [
            item["source_row"]
            for item in rows
            if any(item["payload"].get(header, "") == "" for header in score_headers)
        ]

    @staticmethod
    def _alias_team_conflicts(personal_rows, team_rows):
        alias_teams = defaultdict(set)
        for item in personal_rows:
            payload = item["payload"]
            alias = payload.get("평가자 별칭", "")
            team = payload.get("소속 팀", "")
            if alias and team:
                alias_teams[alias].add(team)
        for item in team_rows:
            payload = item["payload"]
            alias = payload.get("평가자 별칭", "")
            team = payload.get("평가자 소속 팀", "")
            if alias and team:
                alias_teams[alias].add(team)
        return sorted(
            (alias, sorted(teams))
            for alias, teams in alias_teams.items()
            if len(teams) > 1
        )

    def _dashboard_tables(self):
        return sorted(
            table
            for table in connection.introspection.table_names()
            if table.startswith("dashboard_")
        )

    def _assert_raw_table_exists(self):
        if RAW_TABLE not in connection.introspection.table_names():
            raise CommandError(
                f"{RAW_TABLE} 테이블이 없습니다. 먼저 `python manage.py migrate`를 실행하세요."
            )

    def _truncate_dashboard_data(self):
        tables = self._dashboard_tables()
        if not tables:
            raise CommandError("초기화할 dashboard_* 테이블을 찾지 못했습니다.")

        quote = connection.ops.quote_name
        sql = (
            "TRUNCATE TABLE "
            + ", ".join(quote(table) for table in tables)
            + " RESTART IDENTITY CASCADE"
        )
        with connection.cursor() as cursor:
            cursor.execute(sql)

    @staticmethod
    def _create_round(round_name):
        now = timezone.now()
        return EvaluationRound.objects.create(
            name=round_name,
            start_at=now - timedelta(days=1),
            end_at=now,
            status=EvaluationRound.Status.ENDED,
            evaluation_started=True,
            is_locked=True,
            is_current=True,
            team_weight=40,
            personal_weight=60,
        )

    @staticmethod
    def _create_official_templates():
        personal_template = EvaluationTemplate.objects.create(
            name="AX2 공식 개인동료평가",
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
            evaluation_round=None,
            is_active=True,
        )
        for order, title in enumerate(PERSONAL_CRITERIA, start=1):
            EvaluationCriterion.objects.create(
                template=personal_template,
                title=title,
                order=order,
                max_score=5,
                is_required=True,
            )

        team_template = EvaluationTemplate.objects.create(
            name="AX2 공식 팀평가",
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
            evaluation_round=None,
            is_active=True,
        )
        for order, title in enumerate(TEAM_CRITERIA, start=1):
            EvaluationCriterion.objects.create(
                template=team_template,
                title=title,
                order=order,
                max_score=5,
                is_required=True,
            )

    @staticmethod
    def _insert_raw_rows(evaluation_round_id, source):
        sql = f"""
            INSERT INTO {RAW_TABLE}
                (evaluation_round_id, response_type, source_filename, source_sha256, source_row, payload)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        """
        params = [
            (
                evaluation_round_id,
                source["type"],
                source["filename"],
                source["sha256"],
                item["source_row"],
                json.dumps(item["payload"], ensure_ascii=False),
            )
            for item in source["rows"]
        ]
        with connection.cursor() as cursor:
            cursor.executemany(sql, params)
