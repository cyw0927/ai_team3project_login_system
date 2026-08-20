"""Admin dashboard context builder."""

from datetime import timedelta

from django.utils import timezone

from dashboard.models import (
    Assignment,
    EvaluationRound,
    EvaluationTemplate,
    HRTask,
    PersonalEvaluation,
    ResultPublishSetting,
    RoundAttendance,
    Student,
    Team,
    TeamEvaluation,
    TeamMembership,
)
from dashboard.services.official_import_service import official_response_counts


def build_admin_dashboard_context(current_round):
    student_count = Student.objects.filter(is_active=True).count()
    active_team_count = 0
    team_submission_count = 0
    personal_submission_count = 0
    team_required = 0
    personal_required = 0
    has_teams = False
    has_assignment = False
    templates_ready = False
    is_published = False
    current_assignment = None
    workflow_steps = []

    if current_round:
        current_round.status_display = current_round.get_status_display()
        active_teams = list(Team.objects.filter(evaluation_round=current_round, is_active=True))
        active_team_count = len(active_teams)
        memberships = list(
            TeamMembership.objects.filter(team__evaluation_round=current_round, team__is_active=True)
            .select_related("team", "student")
        )
        member_count_by_team = {}
        for membership in memberships:
            member_count_by_team[membership.team_id] = member_count_by_team.get(membership.team_id, 0) + 1

        attendance_map = dict(
            RoundAttendance.objects.filter(
                evaluation_round=current_round,
                student_id__in=[m.student_id for m in memberships],
            ).values_list("student_id", "status")
        )
        for membership in memberships:
            if not membership.student.is_active:
                continue
            attendance_status = attendance_map.get(membership.student_id, RoundAttendance.Status.PRESENT)
            if attendance_status == RoundAttendance.Status.PRESENT:
                team_required += max(active_team_count - 1, 0)
            personal_required += max(member_count_by_team.get(membership.team_id, 0) - 1, 0)

        team_submission_count = TeamEvaluation.objects.filter(
            evaluation_round=current_round, evaluator__is_active=True, is_submitted=True
        ).count()
        personal_submission_count = PersonalEvaluation.objects.filter(
            evaluation_round=current_round, evaluator__is_active=True, is_submitted=True
        ).count()

        # 공식 CSV import 회차는 canonical 조합 수가 아니라 raw 원본 응답 수가 진짜 제출 수다.
        official_counts = official_response_counts(current_round)
        if official_counts:
            team_submission_count = official_counts["team"]
            personal_submission_count = official_counts["personal"]
            team_required = official_counts["team"]
            personal_required = official_counts["personal"]

    required_total = team_required + personal_required
    submitted_total = min(team_submission_count, team_required) + min(personal_submission_count, personal_required)
    overall_percent = round((submitted_total / required_total) * 100) if required_total else 0
    missing_submission_count = max(required_total - submitted_total, 0)

    now = timezone.now()
    assignment_count = Assignment.objects.count()
    attachment_count = Assignment.objects.exclude(attachment="").count()
    in_progress_round_count = EvaluationRound.objects.filter(status=EvaluationRound.Status.IN_PROGRESS).count()
    ending_soon_count = EvaluationRound.objects.filter(
        status=EvaluationRound.Status.IN_PROGRESS,
        end_at__gte=now,
        end_at__lte=now + timedelta(days=2),
    ).count()

    recent_assignments = list(
        Assignment.objects.select_related("evaluation_round")
        .order_by("-evaluation_round__start_at", "-created_at")[:5]
    )
    for assignment in recent_assignments:
        round_obj = assignment.evaluation_round
        assignment.round_status = round_obj.get_status_display()
        assignment.is_current = bool(current_round and round_obj.pk == current_round.pk)
        assignment.has_attachment = bool(assignment.attachment)

    if current_round:
        current_assignment = Assignment.objects.filter(evaluation_round=current_round).select_related("evaluation_round").first()
        has_teams = Team.objects.filter(evaluation_round=current_round, is_active=True).exists()
        has_assignment = Assignment.objects.filter(evaluation_round=current_round).exists()
        has_team_template = EvaluationTemplate.objects.filter(
            evaluation_round=current_round,
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
            is_active=True,
        ).exists()
        has_personal_template = EvaluationTemplate.objects.filter(
            evaluation_round=current_round,
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
            is_active=True,
        ).exists()
        templates_ready = has_team_template and has_personal_template
        publish_setting = ResultPublishSetting.objects.filter(evaluation_round=current_round).first()
        is_published = bool(
            publish_setting
            and (
                publish_setting.is_published
                or (publish_setting.publish_at and publish_setting.publish_at <= timezone.now())
            )
        )

        workflow_steps = [
            {"number": 1, "label": "회차", "detail": "운영 회차 생성", "done": True, "url_name": "admin_rounds"},
            {"number": 2, "label": "팀 편성", "detail": "학생 팀 배정", "done": has_teams, "url_name": "admin_team_assignment"},
            {"number": 3, "label": "과제", "detail": "개별/조별 과제 등록", "done": has_assignment, "url_name": "admin_assignments"},
            {"number": 4, "label": "평가 템플릿", "detail": "팀/개인 템플릿 적용", "done": templates_ready, "url_name": "admin_evaluation_templates"},
            {"number": 5, "label": "평가 시작", "detail": "평가 진행 상태 전환", "done": current_round.evaluation_started, "url_name": "admin_operations"},
            {"number": 6, "label": "결과 공개", "detail": "점수 확인 후 학생 공개", "done": is_published, "url_name": "admin_result_settings"},
        ]
        first_pending_found = False
        for step in workflow_steps:
            step["current"] = False
            if not first_pending_found and not step["done"]:
                step["current"] = True
                first_pending_found = True

    admin_alerts = []
    if current_round:
        if current_round.status == EvaluationRound.Status.IN_PROGRESS:
            remaining = current_round.end_at - now
            if remaining.total_seconds() >= 0 and remaining <= timedelta(days=1):
                hours_left = max(0, int(remaining.total_seconds() // 3600))
                admin_alerts.append({
                    "level": "danger" if hours_left <= 6 else "warning",
                    "icon": "bi-alarm",
                    "title": f"평가 마감 {hours_left}시간 전",
                    "detail": f"{current_round.name} 마감이 임박했습니다.",
                    "url_name": "admin_operations",
                    "action": "운영 확인",
                })
        if missing_submission_count > 0 and current_round.evaluation_started:
            admin_alerts.append({
                "level": "warning", "icon": "bi-person-exclamation",
                "title": f"미제출 평가 {missing_submission_count}건",
                "detail": "아직 제출되지 않은 평가가 있습니다.",
                "url_name": "admin_missing_evaluations", "action": "미제출 확인",
            })
        if not has_teams:
            admin_alerts.append({"level": "info", "icon": "bi-diagram-3", "title": "팀 편성이 필요합니다.", "detail": "현재 회차에 활성 팀이 없습니다.", "url_name": "admin_team_assignment", "action": "팀 편성"})
        if not has_assignment:
            admin_alerts.append({"level": "info", "icon": "bi-folder-plus", "title": "과제가 등록되지 않았습니다.", "detail": "평가 시작 전에 과제를 등록해 주세요.", "url_name": "admin_assignments", "action": "과제 등록"})
        if not templates_ready:
            admin_alerts.append({"level": "info", "icon": "bi-ui-checks-grid", "title": "평가 템플릿이 준비되지 않았습니다.", "detail": "팀 평가와 개인 평가 템플릿을 모두 적용해 주세요.", "url_name": "admin_evaluation_templates", "action": "템플릿 확인"})
        if current_round.status == EvaluationRound.Status.ENDED and not is_published:
            admin_alerts.append({"level": "warning", "icon": "bi-eye-slash", "title": "결과가 아직 공개되지 않았습니다.", "detail": "점수를 확인한 뒤 학생 공개 여부를 설정해 주세요.", "url_name": "admin_result_settings", "action": "공개 설정"})

    growth_tasks = list(
        HRTask.objects.select_related("assignee__user")
        .exclude(status=HRTask.Status.COMPLETED)
        .order_by("due_date", "-updated_at")
    )
    growth_task_summary = {
        "active": sum(1 for task in growth_tasks if task.status == HRTask.Status.IN_PROGRESS),
        "review": sum(1 for task in growth_tasks if task.status == HRTask.Status.REVIEW),
        "overdue": sum(1 for task in growth_tasks if task.is_overdue),
        "scheduled": sum(1 for task in growth_tasks if task.status == HRTask.Status.SCHEDULED),
    }
    growth_attention_tasks = sorted(
        [task for task in growth_tasks if task.status == HRTask.Status.REVIEW or task.is_overdue],
        key=lambda task: (0 if task.status == HRTask.Status.REVIEW else 1, task.due_date or timezone.localdate(), task.id),
    )[:5]

    stats = {
        "student_count": student_count,
        "active_team_count": active_team_count,
        "team_submission_count": team_submission_count,
        "team_required": team_required,
        "personal_submission_count": personal_submission_count,
        "personal_required": personal_required,
        "missing_submission_count": missing_submission_count,
        "overall_percent": overall_percent,
        "assignment_count": assignment_count,
        "attachment_count": attachment_count,
        "in_progress_round_count": in_progress_round_count,
        "ending_soon_count": ending_soon_count,
    }
    return {
        "current_round": current_round,
        "current_assignment": current_assignment,
        "recent_assignments": recent_assignments,
        "workflow_steps": workflow_steps,
        "admin_alerts": admin_alerts,
        "growth_task_summary": growth_task_summary,
        "growth_attention_tasks": growth_attention_tasks,
        "stats": stats,
    }
