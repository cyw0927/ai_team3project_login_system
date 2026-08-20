import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from dashboard.models import (
    EvaluationCriterion,
    EvaluationRound,
    EvaluationTemplate,
    PersonalEvaluation,
    PersonalEvaluationScore,
    RoundAttendance,
    Student,
    StudentResult,
    Team,
    TeamEvaluation,
    TeamEvaluationScore,
    TeamMembership,
    TeamResult,
)


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
        "AX2 공식 개인/팀 평가 CSV를 원본 그대로 적재한 뒤 UI용 학생/팀/평가/결과 투영 데이터를 생성합니다. "
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
        projection = self._build_projection(personal["rows"], team["rows"])

        self._print_preview(personal, team, projection=projection, apply=options["apply"])

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
            personal_template, team_template = self._create_official_templates(
                evaluation_round
            )

            # 원본 167행을 먼저 그대로 보존한다. 아래 canonical/UI 투영은 이 원본을 대체하지 않는다.
            self._insert_raw_rows(evaluation_round.id, personal)
            self._insert_raw_rows(evaluation_round.id, team)

            students, teams = self._create_participants_and_teams(
                evaluation_round, projection
            )
            self._create_canonical_evaluations(
                evaluation_round,
                personal,
                team,
                students,
                teams,
                personal_template,
                team_template,
            )
            self._create_results_from_raw(
                evaluation_round,
                personal,
                team,
                students,
                teams,
                projection,
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("AX2 공식 데이터 초기화/import 완료"))
        self.stdout.write(f"보존 관리자: {', '.join(preserved_admins) or '(없음)'}")
        self.stdout.write(f"삭제된 비관리자 관련 객체 수: {deleted_users}")
        self.stdout.write(f"생성 학생: {len(students)}명 / 팀: {len(teams)}개")
        self.stdout.write(f"개인 원본 응답: {len(personal['rows'])}건")
        self.stdout.write(f"팀 원본 응답: {len(team['rows'])}건")
        self.stdout.write(f"총 원본 응답: {len(personal['rows']) + len(team['rows'])}건")
        self.stdout.write("공식 템플릿: 개인 5문항 / 팀 5문항")
        self.stdout.write(
            self.style.WARNING(
                "원본 167행은 수정하지 않았습니다. "
                "UI용 소속은 원본 표기를 근거로 별도 투영했으며, "
                "중복 응답은 결과 계산에서 각각 1건으로 반영하고 빈 점수만 평균 분모에서 제외했습니다."
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

    def _print_preview(self, personal, team, *, projection, apply):
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
            f"UI 투영 예정: 학생 {len(projection['aliases'])}명 / "
            f"팀 {len(projection['teams'])}개"
        )
        for team_name in sorted(projection["teams"]):
            aliases = sorted(
                alias
                for alias, assigned_team in projection["membership"].items()
                if assigned_team == team_name
            )
            self.stdout.write(f"  - {team_name}: {len(aliases)}명")
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
            f"동일 별칭의 복수 팀 표기: {len(team_conflicts)}명 (원본 그대로 보존)"
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
            self.stdout.write("팀 표기 충돌 예시 / UI 투영 소속:")
            for alias, source_teams in team_conflicts[:5]:
                self.stdout.write(
                    f"  - {alias}: {', '.join(source_teams)} -> "
                    f"{projection['membership'].get(alias, '(없음)')}"
                )

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

    @staticmethod
    def _build_projection(personal_rows, team_rows):
        aliases = set()
        evidence = defaultdict(Counter)
        team_names = set()

        # 평가자 본인이 적은 소속은 직접 증거(가중 2).
        # 개인평가 대상은 같은 팀원을 평가하는 양식이므로 평가자 소속을 간접 증거(가중 1)로 사용한다.
        # 이렇게 하면 평가자로 등장하지 않은 별칭도 원본 관계만으로 소속을 투영할 수 있다.
        for item in personal_rows:
            payload = item["payload"]
            evaluator = payload.get("평가자 별칭", "")
            target = payload.get("평가 대상 팀원 별칭", "")
            team_name = payload.get("소속 팀", "")
            if evaluator:
                aliases.add(evaluator)
            if target:
                aliases.add(target)
            if team_name:
                team_names.add(team_name)
                if evaluator:
                    evidence[evaluator][team_name] += 2
                if target:
                    evidence[target][team_name] += 1

        for item in team_rows:
            payload = item["payload"]
            evaluator = payload.get("평가자 별칭", "")
            team_name = payload.get("평가자 소속 팀", "")
            target_team = payload.get("평가 대상 팀", "")
            if evaluator:
                aliases.add(evaluator)
            if team_name:
                team_names.add(team_name)
                if evaluator:
                    evidence[evaluator][team_name] += 2
            if target_team:
                team_names.add(target_team)

        membership = {}
        for alias in sorted(aliases):
            if not evidence[alias]:
                raise CommandError(f"{alias}의 팀 소속을 원본에서 추론할 수 없습니다.")
            ranked = sorted(
                evidence[alias].items(),
                key=lambda item: (-item[1], item[0]),
            )
            membership[alias] = ranked[0][0]

        return {
            "aliases": sorted(aliases),
            "teams": sorted(team_names),
            "membership": membership,
        }

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
    def _create_official_templates(evaluation_round):
        personal_template = EvaluationTemplate.objects.create(
            name="AX2 공식 개인동료평가",
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
            evaluation_round=evaluation_round,
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
            evaluation_round=evaluation_round,
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
        return personal_template, team_template

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

    @staticmethod
    def _create_participants_and_teams(evaluation_round, projection):
        teams = {
            team_name: Team.objects.create(
                evaluation_round=evaluation_round,
                name=team_name,
                is_active=True,
            )
            for team_name in projection["teams"]
        }

        students = {}
        for index, alias in enumerate(projection["aliases"], start=1):
            user = User(username=f"ax2_official_{index:02d}", first_name=alias, is_active=True)
            user.set_unusable_password()
            user.save()
            student = Student.objects.create(
                user=user,
                is_active=True,
                affiliation="AX2 공식 익명화 데이터",
            )
            TeamMembership.objects.create(
                team=teams[projection["membership"][alias]],
                student=student,
            )
            RoundAttendance.objects.create(
                evaluation_round=evaluation_round,
                student=student,
                status=RoundAttendance.Status.PRESENT,
            )
            students[alias] = student

        return students, teams

    @staticmethod
    def _score_value(raw_value):
        raw_value = (raw_value or "").strip()
        if raw_value == "":
            return None
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise CommandError(f"1~5 정수가 아닌 점수가 있습니다: {raw_value!r}") from exc
        if not 1 <= value <= 5:
            raise CommandError(f"점수 범위를 벗어난 값이 있습니다: {value}")
        return value

    @classmethod
    def _create_canonical_evaluations(
        cls,
        evaluation_round,
        personal,
        team,
        students,
        teams,
        personal_template,
        team_template,
    ):
        personal_criteria = {
            criterion.title: criterion
            for criterion in personal_template.criteria.all()
        }
        team_criteria = {
            criterion.title: criterion
            for criterion in team_template.criteria.all()
        }

        # canonical 테이블은 unique 제약이 있으므로 동일 evaluator-target 원본이 여러 행이면
        # 가장 앞 source_row를 대표 행으로 사용한다. 모든 원본 행은 raw 테이블에 별도로 보존된다.
        personal_groups = defaultdict(list)
        for item in personal["rows"]:
            payload = item["payload"]
            personal_groups[
                (payload["평가자 별칭"], payload["평가 대상 팀원 별칭"])
            ].append(item)

        for (evaluator_alias, target_alias), items in sorted(personal_groups.items()):
            representative = sorted(items, key=lambda item: item["source_row"])[0]
            evaluation = PersonalEvaluation.objects.create(
                evaluation_round=evaluation_round,
                evaluator=students[evaluator_alias],
                target_student=students[target_alias],
                comment=(
                    "AX2 원본 UI 투영. "
                    f"대표 source_row={representative['source_row']}; "
                    f"동일 조합 원본={len(items)}건."
                ),
                is_submitted=True,
                submitted_at=timezone.now(),
            )
            payload = representative["payload"]
            for title in PERSONAL_CRITERIA:
                value = cls._score_value(payload.get(title))
                if value is not None:
                    PersonalEvaluationScore.objects.create(
                        evaluation=evaluation,
                        criterion=personal_criteria[title],
                        score=value,
                    )

        team_groups = defaultdict(list)
        for item in team["rows"]:
            payload = item["payload"]
            team_groups[
                (payload["평가자 별칭"], payload["평가 대상 팀"])
            ].append(item)

        for (evaluator_alias, target_team_name), items in sorted(team_groups.items()):
            representative = sorted(items, key=lambda item: item["source_row"])[0]
            evaluation = TeamEvaluation.objects.create(
                evaluation_round=evaluation_round,
                evaluator=students[evaluator_alias],
                target_team=teams[target_team_name],
                comment=(
                    "AX2 원본 UI 투영. "
                    f"대표 source_row={representative['source_row']}; "
                    f"동일 조합 원본={len(items)}건."
                ),
                is_submitted=True,
                submitted_at=timezone.now(),
            )
            payload = representative["payload"]
            for title in TEAM_CRITERIA:
                value = cls._score_value(payload.get(title))
                if value is not None:
                    TeamEvaluationScore.objects.create(
                        evaluation=evaluation,
                        criterion=team_criteria[title],
                        score=value,
                    )

    @classmethod
    def _create_results_from_raw(
        cls,
        evaluation_round,
        personal,
        team,
        students,
        teams,
        projection,
    ):
        team_score_values = defaultdict(list)
        for item in team["rows"]:
            payload = item["payload"]
            target_team = payload["평가 대상 팀"]
            for title in TEAM_CRITERIA:
                value = cls._score_value(payload.get(title))
                if value is not None:
                    team_score_values[target_team].append(value)

        team_results = []
        team_average = {}
        for team_name, team_obj in teams.items():
            values = team_score_values.get(team_name, [])
            avg = Decimal(str(sum(values) / len(values))) if values else Decimal("0")
            avg = avg.quantize(Decimal("0.01"))
            team_average[team_name] = avg
            result = TeamResult.objects.create(
                evaluation_round=evaluation_round,
                team=team_obj,
                score=avg,
                is_excluded=not bool(values),
            )
            if values:
                team_results.append(result)

        cls._apply_competition_rank(team_results, score_attr="score")

        personal_score_values = defaultdict(list)
        for item in personal["rows"]:
            payload = item["payload"]
            target_alias = payload["평가 대상 팀원 별칭"]
            for title in PERSONAL_CRITERIA:
                value = cls._score_value(payload.get(title))
                if value is not None:
                    personal_score_values[target_alias].append(value)

        student_results = []
        personal_weight = Decimal(evaluation_round.personal_weight) / Decimal("100")
        team_weight = Decimal(evaluation_round.team_weight) / Decimal("100")

        for alias, student in students.items():
            values = personal_score_values.get(alias, [])
            personal_avg = (
                Decimal(str(sum(values) / len(values))).quantize(Decimal("0.01"))
                if values
                else Decimal("0")
            )
            team_name = projection["membership"][alias]
            team_avg = team_average.get(team_name, Decimal("0"))
            excluded = not bool(values) or not bool(team_score_values.get(team_name))
            base_score = (
                personal_avg * personal_weight + team_avg * team_weight
            ).quantize(Decimal("0.01"))

            result = StudentResult.objects.create(
                evaluation_round=evaluation_round,
                student=student,
                team_score=team_avg,
                personal_score=personal_avg,
                base_score=base_score,
                final_score=base_score,
                is_excluded=excluded,
            )
            if not excluded:
                student_results.append(result)

        cls._apply_student_rank(student_results)

    @staticmethod
    def _apply_competition_rank(results, score_attr):
        ordered = sorted(
            results,
            key=lambda result: getattr(result, score_attr),
            reverse=True,
        )
        previous = None
        rank = 0
        for index, result in enumerate(ordered, start=1):
            value = getattr(result, score_attr)
            if value != previous:
                rank = index
                previous = value
            result.rank = rank
            result.save(update_fields=["rank", "updated_at"])

    @staticmethod
    def _apply_student_rank(results):
        ordered = sorted(
            results,
            key=lambda result: (result.final_score, result.personal_score),
            reverse=True,
        )
        previous = None
        rank = 0
        for index, result in enumerate(ordered, start=1):
            key = (result.final_score, result.personal_score)
            if key != previous:
                rank = index
                previous = key
            result.rank = rank
            result.save(update_fields=["rank", "updated_at"])
