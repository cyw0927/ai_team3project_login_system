from collections import Counter

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Count

from dashboard.models import (
    Assignment,
    EvaluationRound,
    EvaluationTemplate,
    PersonalEvaluation,
    RoundAttendance,
    Student,
    StudentResult,
    Team,
    TeamAssignmentSubmission,
    TeamEvaluation,
    TeamMembership,
    TeamResult,
)


RAW_TABLE = "dashboard_officialevaluationresponse"


class Command(BaseCommand):
    help = "현재 AX2 회차의 화면별 핵심 수치가 서로 모순되지 않는지 점검합니다."

    def handle(self, *args, **options):
        round_obj = (
            EvaluationRound.objects.filter(is_current=True).order_by("-start_at", "-id").first()
            or EvaluationRound.objects.order_by("-start_at", "-id").first()
        )
        if not round_obj:
            self.stdout.write(self.style.ERROR("평가 회차가 없습니다."))
            return

        errors = []
        warnings = []
        ok = []

        total_students = Student.objects.count()
        active_students = Student.objects.filter(is_active=True, user__is_active=True).count()
        teams = list(Team.objects.filter(evaluation_round=round_obj, is_active=True).order_by("name"))
        memberships = list(
            TeamMembership.objects.filter(team__evaluation_round=round_obj, team__is_active=True)
            .select_related("team", "student__user")
        )
        membership_ids = [m.student_id for m in memberships]
        distinct_members = len(set(membership_ids))
        team_sizes = Counter(m.team.name for m in memberships)

        self.stdout.write(self.style.MIGRATE_HEADING(f"AX2 데이터 일관성 점검: {round_obj.name}"))
        self.stdout.write(f"전체 수강생: {total_students} / 활성: {active_students}")
        self.stdout.write(f"활성 팀: {len(teams)} / 팀 배정 학생: {distinct_members}")
        self.stdout.write("팀별 인원: " + ", ".join(f"{name} {count}명" for name, count in sorted(team_sizes.items())))

        if len(membership_ids) != distinct_members:
            errors.append(f"한 회차에 중복 팀 배정이 있습니다: membership {len(membership_ids)}건 / 학생 {distinct_members}명")
        else:
            ok.append("회차 내 학생별 팀 배정은 1개입니다.")

        if active_students != distinct_members:
            warnings.append(
                f"활성 수강생 {active_students}명과 현재 회차 팀 배정 학생 {distinct_members}명이 다릅니다."
            )
        else:
            ok.append("활성 수강생 수와 현재 회차 배정 학생 수가 같습니다.")

        present_ids = set(
            RoundAttendance.objects.filter(
                evaluation_round=round_obj,
                status=RoundAttendance.Status.PRESENT,
                student_id__in=membership_ids,
            ).values_list("student_id", flat=True)
        )
        team_count = len(teams)
        expected_team = sum(max(team_count - 1, 0) for sid in set(membership_ids) if sid in present_ids)
        expected_personal = sum(size * max(size - 1, 0) for size in team_sizes.values())

        submitted_team = TeamEvaluation.objects.filter(
            evaluation_round=round_obj,
            evaluator__is_active=True,
            is_submitted=True,
        ).count()
        submitted_personal = PersonalEvaluation.objects.filter(
            evaluation_round=round_obj,
            evaluator__is_active=True,
            is_submitted=True,
        ).count()

        self.stdout.write("")
        self.stdout.write(
            f"팀평가 제출: {submitted_team}/{expected_team} / 미제출 {max(expected_team - submitted_team, 0)}"
        )
        self.stdout.write(
            f"개인평가 제출: {submitted_personal}/{expected_personal} / 미제출 {max(expected_personal - submitted_personal, 0)}"
        )
        required_total = expected_team + expected_personal
        submitted_total = min(submitted_team, expected_team) + min(submitted_personal, expected_personal)
        completion = round((submitted_total / required_total) * 100) if required_total else 0
        self.stdout.write(f"통합 진행률: {submitted_total}/{required_total} = {completion}%")

        self_target_team = 0
        for evaluation in TeamEvaluation.objects.filter(evaluation_round=round_obj).select_related("target_team"):
            if evaluation.target_team.memberships.filter(student_id=evaluation.evaluator_id).exists():
                self_target_team += 1
        if self_target_team:
            errors.append(f"자기 팀을 평가한 canonical 팀평가가 {self_target_team}건 남아 있습니다.")
        else:
            ok.append("자기 팀 평가 canonical 행은 없습니다.")

        student_result_count = StudentResult.objects.filter(evaluation_round=round_obj).count()
        team_result_count = TeamResult.objects.filter(evaluation_round=round_obj).count()
        if student_result_count != distinct_members:
            errors.append(f"학생 결과 {student_result_count}건 != 팀 배정 학생 {distinct_members}명")
        else:
            ok.append("학생 결과 건수와 팀 배정 학생 수가 같습니다.")
        if team_result_count != team_count:
            errors.append(f"팀 결과 {team_result_count}건 != 활성 팀 {team_count}개")
        else:
            ok.append("팀 결과 건수와 활성 팀 수가 같습니다.")

        team_templates = EvaluationTemplate.objects.filter(
            evaluation_round=round_obj,
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
            is_active=True,
        )
        personal_templates = EvaluationTemplate.objects.filter(
            evaluation_round=round_obj,
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
            is_active=True,
        )
        team_criteria = sum(template.criteria.count() for template in team_templates)
        personal_criteria = sum(template.criteria.count() for template in personal_templates)
        if team_templates.count() != 1 or team_criteria != 5:
            errors.append(f"팀 템플릿 상태 이상: 템플릿 {team_templates.count()}개 / 문항 {team_criteria}개")
        else:
            ok.append("팀 평가 템플릿 1개 / 5문항입니다.")
        if personal_templates.count() != 1 or personal_criteria != 5:
            errors.append(f"개인 템플릿 상태 이상: 템플릿 {personal_templates.count()}개 / 문항 {personal_criteria}개")
        else:
            ok.append("개인 평가 템플릿 1개 / 5문항입니다.")

        assignment = Assignment.objects.filter(
            evaluation_round=round_obj,
            assignment_type=Assignment.AssignmentType.TEAM,
        ).first()
        if assignment:
            submission_count = TeamAssignmentSubmission.objects.filter(assignment=assignment).count()
            if submission_count != team_count:
                warnings.append(f"조별과제 제출 {submission_count}/{team_count}: 준비도 화면과 확인 필요")
            else:
                ok.append(f"조별과제 제출 {submission_count}/{team_count}입니다.")
        else:
            warnings.append("현재 회차 조별과제가 없습니다.")

        if RAW_TABLE in connection.introspection.table_names():
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT response_type, COUNT(*) FROM {RAW_TABLE} WHERE evaluation_round_id=%s GROUP BY response_type",
                    [round_obj.id],
                )
                raw_counts = dict(cursor.fetchall())
            if raw_counts:
                rendered = ", ".join(f"{key}={value}" for key, value in sorted(raw_counts.items()))
                self.stdout.write(f"원본 보관 행: {rendered}")
                if raw_counts.get("personal_source") == 101 and raw_counts.get("team_source") == 66:
                    ok.append("AX2 원본 101+66행이 source archive로 보존되어 있습니다.")
                elif raw_counts.get("personal") == 101 and raw_counts.get("team") == 66:
                    warnings.append("legacy 완료-import 타입(team/personal)이 남아 있어 진행률을 100%로 오인할 수 있습니다.")

        duplicate_names = list(
            Student.objects.values("user__first_name")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )
        if duplicate_names:
            warnings.append("표시명이 완전히 같은 학생이 남아 있습니다: " + ", ".join(
                f"{row['user__first_name']}×{row['count']}" for row in duplicate_names
            ))
        else:
            ok.append("현재 학생 표시명은 서로 구분됩니다.")

        self.stdout.write("")
        for message in ok:
            self.stdout.write(self.style.SUCCESS(f"[OK] {message}"))
        for message in warnings:
            self.stdout.write(self.style.WARNING(f"[WARN] {message}"))
        for message in errors:
            self.stdout.write(self.style.ERROR(f"[ERROR] {message}"))

        self.stdout.write("")
        if errors:
            self.stdout.write(self.style.ERROR(f"점검 실패: 오류 {len(errors)}건 / 경고 {len(warnings)}건"))
        else:
            self.stdout.write(self.style.SUCCESS(f"점검 완료: 오류 0건 / 경고 {len(warnings)}건"))
