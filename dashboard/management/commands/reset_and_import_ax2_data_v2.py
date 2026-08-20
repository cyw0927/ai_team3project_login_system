from collections import Counter, defaultdict
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import CommandError
from django.utils import timezone

from dashboard.management.commands.reset_and_import_ax2_data import (
    Command as BaseAX2ImportCommand,
    PERSONAL_CRITERIA,
    TEAM_CRITERIA,
)
from dashboard.models import (
    Assignment,
    EvaluationCriterion,
    EvaluationTemplate,
    PersonalEvaluation,
    PersonalEvaluationScore,
    RoundAttendance,
    Student,
    StudentResult,
    Team,
    TeamAssignmentSubmission,
    TeamEvaluation,
    TeamEvaluationScore,
    TeamMembership,
    TeamResult,
)


class Command(BaseAX2ImportCommand):
    help = (
        "AX2 공식 데이터를 다시 초기화/import합니다. 동일 별칭이 여러 팀에 등장하면 "
        "서로 다른 학생으로 분리하고 A/B/C 접미사를 붙이며, 실제 미제출 조합을 유지합니다."
    )

    @staticmethod
    def _build_projection(personal_rows, team_rows):
        participants = set()
        team_names = set()
        occurrence = defaultdict(Counter)

        # 개인평가는 같은 팀 내부 평가이므로 대상 학생의 팀도 평가자 소속 팀과 같다.
        for item in personal_rows:
            payload = item["payload"]
            team_name = payload.get("소속 팀", "")
            evaluator = payload.get("평가자 별칭", "")
            target = payload.get("평가 대상 팀원 별칭", "")
            if team_name:
                team_names.add(team_name)
            if evaluator and team_name:
                participants.add((evaluator, team_name))
                occurrence[evaluator][team_name] += 1
            if target and team_name:
                participants.add((target, team_name))
                occurrence[target][team_name] += 1

        for item in team_rows:
            payload = item["payload"]
            evaluator = payload.get("평가자 별칭", "")
            evaluator_team = payload.get("평가자 소속 팀", "")
            target_team = payload.get("평가 대상 팀", "")
            if evaluator_team:
                team_names.add(evaluator_team)
            if target_team:
                team_names.add(target_team)
            if evaluator and evaluator_team:
                participants.add((evaluator, evaluator_team))
                occurrence[evaluator][evaluator_team] += 1

        if not participants:
            raise CommandError("AX2 학생 식별 정보를 찾지 못했습니다.")

        teams_by_alias = defaultdict(list)
        for alias, team_name in participants:
            teams_by_alias[alias].append(team_name)

        display_names = {}
        duplicate_aliases = {}
        for alias, team_list in sorted(teams_by_alias.items()):
            ranked_teams = sorted(
                set(team_list),
                key=lambda team_name: (-occurrence[alias][team_name], team_name),
            )
            if len(ranked_teams) == 1:
                display_names[(alias, ranked_teams[0])] = alias
                continue

            duplicate_aliases[alias] = ranked_teams
            for index, team_name in enumerate(ranked_teams):
                # 가장 많이 관측된 소속을 A, 그 다음을 B/C... 로 표시한다.
                suffix = chr(ord("A") + index)
                display_names[(alias, team_name)] = f"{alias}{suffix}"

        membership = {participant: participant[1] for participant in participants}
        return {
            "participants": sorted(participants, key=lambda item: (item[1], item[0])),
            "teams": sorted(team_names),
            "membership": membership,
            "display_names": display_names,
            "duplicate_aliases": duplicate_aliases,
            "occurrence": occurrence,
        }

    def _print_preview(self, personal, team, *, projection, apply):
        mode = "실제 반영" if apply else "DRY-RUN"
        self.stdout.write(self.style.MIGRATE_HEADING(f"AX2 재구축 import 미리보기 ({mode})"))
        self.stdout.write(f"개인 CSV: {personal['filename']} / {len(personal['rows'])}건")
        self.stdout.write(f"팀 CSV: {team['filename']} / {len(team['rows'])}건")
        self.stdout.write(f"총 원본 응답: {len(personal['rows']) + len(team['rows'])}건")
        self.stdout.write("")
        self.stdout.write(
            f"별칭+팀 기준 학생: {len(projection['participants'])}명 / 팀 {len(projection['teams'])}개"
        )
        for team_name in projection["teams"]:
            count = sum(1 for _, assigned_team in projection["participants"] if assigned_team == team_name)
            self.stdout.write(f"  - {team_name}: {count}명")

        duplicate_aliases = projection["duplicate_aliases"]
        self.stdout.write("")
        self.stdout.write(f"팀이 다른 동명이 별칭: {len(duplicate_aliases)}명")
        for alias, team_names in duplicate_aliases.items():
            rendered = []
            for team_name in team_names:
                rendered.append(
                    f"{team_name}={projection['display_names'][(alias, team_name)]}"
                )
            self.stdout.write(f"  - {alias}: " + ", ".join(rendered))

        personal_duplicates = self._duplicate_groups(
            personal["rows"], ("평가자 별칭", "소속 팀", "평가 대상 팀원 별칭")
        )
        team_duplicates = self._duplicate_groups(
            team["rows"], ("평가자 별칭", "평가자 소속 팀", "평가 대상 팀")
        )
        self.stdout.write("")
        self.stdout.write(
            f"중복 원본 그룹: 개인 {len(personal_duplicates)} / 팀 {len(team_duplicates)} (raw는 모두 보존)"
        )
        self.stdout.write("미제출은 import 후 실제 팀 구성과 canonical 제출 조합으로 계산합니다.")

    @staticmethod
    def _create_official_templates(evaluation_round):
        # 회차 적용 템플릿
        personal_template = EvaluationTemplate.objects.create(
            name="AX2 공식 개인동료평가",
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
            evaluation_round=evaluation_round,
            is_active=True,
        )
        team_template = EvaluationTemplate.objects.create(
            name="AX2 공식 팀평가",
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
            evaluation_round=evaluation_round,
            is_active=True,
        )

        # 템플릿 라이브러리에서도 볼 수 있도록 공통 템플릿 2개를 함께 만든다.
        common_personal = EvaluationTemplate.objects.create(
            name="AX2 공식 개인동료평가 (공통)",
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
            evaluation_round=None,
            is_active=True,
        )
        common_team = EvaluationTemplate.objects.create(
            name="AX2 공식 팀평가 (공통)",
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
            evaluation_round=None,
            is_active=True,
        )

        for order, title in enumerate(PERSONAL_CRITERIA, start=1):
            for template in (personal_template, common_personal):
                EvaluationCriterion.objects.create(
                    template=template,
                    title=title,
                    order=order,
                    max_score=5,
                    is_required=True,
                )
        for order, title in enumerate(TEAM_CRITERIA, start=1):
            for template in (team_template, common_team):
                EvaluationCriterion.objects.create(
                    template=template,
                    title=title,
                    order=order,
                    max_score=5,
                    is_required=True,
                )
        return personal_template, team_template

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
        for index, participant in enumerate(projection["participants"], start=1):
            alias, team_name = participant
            display_name = projection["display_names"][participant]
            user = User(
                username=f"ax2_official_{index:02d}",
                first_name=display_name,
                is_active=True,
            )
            user.set_unusable_password()
            user.save()
            student = Student.objects.create(
                user=user,
                is_active=True,
                affiliation="AX2 공식 익명화 데이터",
            )
            TeamMembership.objects.create(team=teams[team_name], student=student)
            RoundAttendance.objects.create(
                evaluation_round=evaluation_round,
                student=student,
                status=RoundAttendance.Status.PRESENT,
            )
            students[participant] = student
        return students, teams

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
        personal_criteria = {c.title: c for c in personal_template.criteria.all()}
        team_criteria = {c.title: c for c in team_template.criteria.all()}

        personal_groups = defaultdict(list)
        for item in personal["rows"]:
            payload = item["payload"]
            team_name = payload["소속 팀"]
            evaluator_key = (payload["평가자 별칭"], team_name)
            target_key = (payload["평가 대상 팀원 별칭"], team_name)
            personal_groups[(evaluator_key, target_key)].append(item)

        for (evaluator_key, target_key), items in sorted(personal_groups.items()):
            representative = min(items, key=lambda item: item["source_row"])
            evaluation = PersonalEvaluation.objects.create(
                evaluation_round=evaluation_round,
                evaluator=students[evaluator_key],
                target_student=students[target_key],
                comment=(
                    "AX2 원본 투영. "
                    f"대표 source_row={representative['source_row']}; 동일 조합 원본={len(items)}건."
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
            evaluator_key = (payload["평가자 별칭"], payload["평가자 소속 팀"])
            team_groups[(evaluator_key, payload["평가 대상 팀"])].append(item)

        for (evaluator_key, target_team_name), items in sorted(team_groups.items()):
            representative = min(items, key=lambda item: item["source_row"])
            evaluation = TeamEvaluation.objects.create(
                evaluation_round=evaluation_round,
                evaluator=students[evaluator_key],
                target_team=teams[target_team_name],
                comment=(
                    "AX2 원본 투영. "
                    f"대표 source_row={representative['source_row']}; 동일 조합 원본={len(items)}건."
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
            for title in TEAM_CRITERIA:
                value = cls._score_value(payload.get(title))
                if value is not None:
                    team_score_values[payload["평가 대상 팀"]].append(value)

        team_results = []
        team_average = {}
        for team_name, team_obj in teams.items():
            values = team_score_values.get(team_name, [])
            avg = (
                Decimal(str(sum(values) / len(values))).quantize(Decimal("0.01"))
                if values else Decimal("0")
            )
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
            target_key = (payload["평가 대상 팀원 별칭"], payload["소속 팀"])
            for title in PERSONAL_CRITERIA:
                value = cls._score_value(payload.get(title))
                if value is not None:
                    personal_score_values[target_key].append(value)

        personal_weight = Decimal(evaluation_round.personal_weight) / Decimal("100")
        team_weight = Decimal(evaluation_round.team_weight) / Decimal("100")
        student_results = []
        for participant, student in students.items():
            values = personal_score_values.get(participant, [])
            personal_avg = (
                Decimal(str(sum(values) / len(values))).quantize(Decimal("0.01"))
                if values else Decimal("0")
            )
            team_name = participant[1]
            team_avg = team_average.get(team_name, Decimal("0"))
            excluded = not bool(values) or not bool(team_score_values.get(team_name))
            base_score = (personal_avg * personal_weight + team_avg * team_weight).quantize(
                Decimal("0.01")
            )
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

        # 이관된 과거 회차의 과제는 4개 팀 모두 제출 완료로 처리한다.
        assignment = Assignment.objects.create(
            evaluation_round=evaluation_round,
            assignment_type=Assignment.AssignmentType.TEAM,
            title="AX2 2차 프로젝트 조별과제",
            description="AX2 공식 데이터 이관 시 과제 제출 완료 처리",
        )
        for team_name, team_obj in teams.items():
            first_member = (
                TeamMembership.objects.filter(team=team_obj)
                .select_related("student")
                .order_by("id")
                .first()
            )
            TeamAssignmentSubmission.objects.create(
                assignment=assignment,
                team=team_obj,
                submitted_by=first_member.student if first_member else None,
                note="AX2 공식 데이터 이관: 제출 완료",
                submitted_at=timezone.now(),
            )
