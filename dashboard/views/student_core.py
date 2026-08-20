"""Student dashboard and team overview views."""

from django.shortcuts import render
from django.utils import timezone

from .common import (
    _active_announcements,
    _attendance_for,
    _base_context,
    _decorate_assignment,
    _display_round_for_student,
    _student_progress,
    _student_team,
    student_required,
)
from ..models import (
    AdminStudentComment,
    AnnouncementRead,
    Assignment,
    EvaluationRound,
    HRTask,
    InternalMessage,
    PersonalEvaluation,
    ResultPublishSetting,
    RoundAttendance,
    SelfProjectReview,
    StudentAssignmentSubmission,
    StudentResult,
    TeamAssignmentSubmission,
    TeamEvaluation,
    TeamMembership,
)


@student_required
def student_home(request):
    current_round = _display_round_for_student()
    my_team = _student_team(request.student, current_round) if current_round else None
    assignment = None
    assignments = []
    assignment_rows = []
    if current_round:
        assignments = [
            _decorate_assignment(item)
            for item in Assignment.objects.filter(
                evaluation_round=current_round
            ).select_related("evaluation_round")
        ]
        assignment = assignments[0] if assignments else None
        current_round.status_display = current_round.get_status_display()

        for item in assignments:
            if item.assignment_type == Assignment.AssignmentType.TEAM:
                submitted = bool(
                    my_team
                    and TeamAssignmentSubmission.objects.filter(
                        assignment=item,
                        team=my_team,
                    ).exists()
                )
            else:
                submitted = StudentAssignmentSubmission.objects.filter(
                    assignment=item,
                    student=request.student,
                ).exists()
            assignment_rows.append({"assignment": item, "submitted": submitted})

    progress = _student_progress(request.student, current_round, my_team)
    team_members = []
    if my_team:
        memberships = (
            TeamMembership.objects.filter(team=my_team)
            .select_related("student__user")
            .order_by("student__user__first_name", "student__user__username")
        )
        for membership in memberships:
            member = membership.student
            member.team_role = membership.role.strip() or (
                "팀장" if membership.is_leader else "팀원"
            )
            team_members.append(member)

    attendance = _attendance_for(request.student, current_round) if current_round else None
    absent_from_team_eval = bool(
        attendance
        and attendance.status in {RoundAttendance.Status.ABSENT, RoundAttendance.Status.EXCUSED}
    )
    round_in_progress = bool(
        current_round and current_round.status == EvaluationRound.Status.IN_PROGRESS
    )
    round_ended = bool(current_round and current_round.status == EvaluationRound.Status.ENDED)
    team_eval_available = bool(
        round_in_progress
        and current_round.evaluation_started
        and not current_round.is_locked
        and my_team
        and not absent_from_team_eval
    )
    personal_eval_available = bool(
        round_in_progress
        and current_round.evaluation_started
        and not current_round.is_locked
        and my_team
        and (
            absent_from_team_eval
            or progress["team_total"] == progress["team_completed"]
        )
    )

    result_available = False
    received_comment_count = 0
    admin_feedback_available = False
    self_review_completed = False
    feedback_written_count = 0
    if current_round:
        publish_setting = ResultPublishSetting.objects.filter(
            evaluation_round=current_round
        ).first()
        now = timezone.now()
        result_available = bool(
            publish_setting
            and (
                publish_setting.is_published
                or (publish_setting.publish_at and publish_setting.publish_at <= now)
            )
            and StudentResult.objects.filter(
                evaluation_round=current_round,
                student=request.student,
                is_excluded=False,
            ).exists()
        )
        if result_available and publish_setting and publish_setting.show_comments:
            received_comment_count = PersonalEvaluation.objects.filter(
                evaluation_round=current_round,
                target_student=request.student,
                is_submitted=True,
            ).exclude(comment="").count()
            admin_feedback_available = AdminStudentComment.objects.filter(
                evaluation_round=current_round,
                student=request.student,
            ).exclude(comment="").exists()
        self_review_completed = SelfProjectReview.objects.filter(
            evaluation_round=current_round,
            student=request.student,
        ).exists()
        feedback_written_count = (
            TeamEvaluation.objects.filter(
                evaluation_round=current_round,
                evaluator=request.student,
                is_submitted=True,
            ).exclude(comment="").count()
            + PersonalEvaluation.objects.filter(
                evaluation_round=current_round,
                evaluator=request.student,
                is_submitted=True,
            ).exclude(comment="").count()
        )

    pending_assignment_count = sum(1 for row in assignment_rows if not row["submitted"])
    assignment_completed_count = len(assignment_rows) - pending_assignment_count
    team_remaining_count = max(0, progress["team_total"] - progress["team_completed"])
    personal_remaining_count = max(
        0,
        progress["personal_total"] - progress["personal_completed"],
    )
    todo_total_count = len(assignment_rows) + progress["team_total"] + progress["personal_total"]
    todo_completed_count = (
        assignment_completed_count
        + progress["team_completed"]
        + progress["personal_completed"]
    )
    todo_remaining_count = max(0, todo_total_count - todo_completed_count)

    evaluation_edit_status = {
        "level": "waiting",
        "label": "평가 대기",
        "detail": "평가가 시작되면 입력할 수 있습니다.",
        "editable": False,
    }
    if current_round:
        all_eval_done = bool(
            (progress["team_total"] == 0 or progress["team_completed"] >= progress["team_total"])
            and (
                progress["personal_total"] == 0
                or progress["personal_completed"] >= progress["personal_total"]
            )
        )
        if current_round.status == EvaluationRound.Status.ENDED:
            evaluation_edit_status = {
                "level": "closed",
                "label": "수정 종료",
                "detail": "회차가 종료되어 평가를 수정할 수 없습니다.",
                "editable": False,
            }
        elif current_round.is_locked:
            evaluation_edit_status = {
                "level": "paused",
                "label": "평가 일시 중단",
                "detail": "관리자가 재개하면 기존 평가를 다시 수정할 수 있습니다.",
                "editable": False,
            }
        elif not current_round.evaluation_started:
            evaluation_edit_status = {
                "level": "waiting",
                "label": "평가 시작 전",
                "detail": "관리자가 평가를 시작하면 입력할 수 있습니다.",
                "editable": False,
            }
        elif all_eval_done:
            evaluation_edit_status = {
                "level": "complete",
                "label": "제출 완료 · 수정 가능",
                "detail": "평가 종료 전까지 제출한 내용을 다시 수정할 수 있습니다.",
                "editable": True,
            }
        else:
            evaluation_edit_status = {
                "level": "active",
                "label": "평가 진행 중",
                "detail": "임시 저장하거나 최종 제출할 수 있으며, 종료 전에는 다시 수정할 수 있습니다.",
                "editable": True,
            }

    deadline = None
    if current_round:
        remaining_seconds = int((current_round.end_at - timezone.now()).total_seconds())
        if remaining_seconds <= 0:
            deadline = {
                "label": "마감",
                "detail": "평가 기간이 종료되었습니다.",
                "level": "closed",
            }
        elif remaining_seconds <= 6 * 60 * 60:
            hours = max(1, (remaining_seconds + 3599) // 3600)
            deadline = {
                "label": f"{hours}시간 남음",
                "detail": "마감이 임박했습니다. 남은 항목을 확인하세요.",
                "level": "critical",
            }
        elif remaining_seconds <= 24 * 60 * 60:
            hours = max(1, (remaining_seconds + 3599) // 3600)
            deadline = {
                "label": f"{hours}시간 남음",
                "detail": "오늘 안에 평가와 제출을 마무리해 주세요.",
                "level": "warning",
            }
        else:
            days = max(1, (remaining_seconds + 86399) // 86400)
            deadline = {
                "label": f"D-{days}",
                "detail": f"{current_round.end_at:%m.%d %H:%M} 마감",
                "level": "normal",
            }

    active_announcements = _active_announcements(request.student)
    recent_announcements = list(active_announcements[:3])
    read_announcement_ids = set(
        AnnouncementRead.objects.filter(
            student=request.student,
            announcement__in=active_announcements,
        ).values_list("announcement_id", flat=True)
    )
    unread_announcements = [
        item for item in active_announcements if item.id not in read_announcement_ids
    ]
    unread_announcement_count = len(unread_announcements)
    urgent_announcement_count = sum(
        1
        for item in unread_announcements
        if item.priority == item.Priority.URGENT
    )
    unread_message_count = InternalMessage.objects.filter(
        recipient=request.student,
        read_at__isnull=True,
        recalled_at__isnull=True,
    ).count()

    growth_task_preview = list(
        HRTask.objects.filter(assignee=request.student)
        .exclude(status=HRTask.Status.COMPLETED)
        .order_by("due_date", "-created_at")[:3]
    )

    return render(
        request,
        "student/home.html",
        _base_context(
            current_round=current_round,
            my_team=my_team,
            assignment=assignment,
            assignments=assignments,
            growth_task_preview=growth_task_preview,
            assignment_rows=assignment_rows,
            pending_assignment_count=pending_assignment_count,
            progress=progress,
            team_members=team_members,
            team_eval_available=team_eval_available,
            personal_eval_available=personal_eval_available,
            recent_announcements=recent_announcements,
            attendance=attendance,
            absent_from_team_eval=absent_from_team_eval,
            round_in_progress=round_in_progress,
            round_ended=round_ended,
            result_available=result_available,
            received_comment_count=received_comment_count,
            admin_feedback_available=admin_feedback_available,
            self_review_completed=self_review_completed,
            feedback_written_count=feedback_written_count,
            unread_message_count=unread_message_count,
            unread_announcement_count=unread_announcement_count,
            urgent_announcement_count=urgent_announcement_count,
            deadline=deadline,
            evaluation_edit_status=evaluation_edit_status,
            todo_total_count=todo_total_count,
            todo_completed_count=todo_completed_count,
            todo_remaining_count=todo_remaining_count,
            team_remaining_count=team_remaining_count,
            personal_remaining_count=personal_remaining_count,
        ),
    )


@student_required
def student_team_info(request):
    evaluation_round = _display_round_for_student()
    team = _student_team(request.student, evaluation_round) if evaluation_round else None
    team_members = []
    if team:
        team.status_display = "활동 중" if team.is_active else "비활성"
        memberships = (
            TeamMembership.objects.filter(team=team)
            .select_related("student__user")
            .order_by("student__user__first_name", "student__user__username")
        )
        for membership in memberships:
            member = membership.student
            member.team_role = membership.role.strip() or (
                "팀장" if membership.is_leader else "팀원"
            )
            member.is_team_leader = membership.is_leader
            team_members.append(member)

    return render(
        request,
        "student/team_info.html",
        _base_context(
            evaluation_round=evaluation_round,
            team=team,
            team_members=team_members,
        ),
    )
