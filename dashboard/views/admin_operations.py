"""Admin round operations and attendance views."""

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .common import _base_context, _sync_round_statuses, admin_required
from ..models import EvaluationRound, EvaluationTemplate, RoundAttendance, Student, TeamMembership


@admin_required
def admin_operations(request):
    _sync_round_statuses()
    rounds = list(
        EvaluationRound.objects.all()
        .prefetch_related("teams", "evaluation_templates")
        .order_by("-start_at")
    )
    now = timezone.now()
    for evaluation_round in rounds:
        assignment = evaluation_round.assignments.first()
        evaluation_round.status_display = evaluation_round.get_status_display()
        evaluation_round.assignment_obj = assignment
        evaluation_round.assignment_title = assignment.title if assignment else ""
        evaluation_round.team_count = evaluation_round.teams.filter(is_active=True).count()
        evaluation_round.template_count = evaluation_round.evaluation_templates.filter(is_active=True).count()
        evaluation_round.team_template_count = evaluation_round.evaluation_templates.filter(
            is_active=True, evaluation_type=EvaluationTemplate.EvaluationType.TEAM
        ).count()
        evaluation_round.personal_template_count = evaluation_round.evaluation_templates.filter(
            is_active=True, evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL
        ).count()
        evaluation_round.can_edit = evaluation_round.status == EvaluationRound.Status.SCHEDULED
        evaluation_round.can_round_start = evaluation_round.status == EvaluationRound.Status.SCHEDULED
        evaluation_round.can_evaluation_start = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and not evaluation_round.evaluation_started
        evaluation_round.can_end = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started
        evaluation_round.can_reopen = evaluation_round.status == EvaluationRound.Status.ENDED
        evaluation_round.can_lock = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started and not evaluation_round.is_locked
        evaluation_round.can_unlock = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started and evaluation_round.is_locked
        evaluation_round.ready_checks = {
            "assignment": bool(assignment),
            "teams": evaluation_round.team_count > 0,
            "team_template": evaluation_round.team_template_count > 0,
            "personal_template": evaluation_round.personal_template_count > 0,
        }
        evaluation_round.ready_count = sum(evaluation_round.ready_checks.values())
        evaluation_round.ready_percent = int(evaluation_round.ready_count / 4 * 100)
        if evaluation_round.status == EvaluationRound.Status.SCHEDULED:
            evaluation_round.time_label = "시작 전 · 과제 등록 가능"
        elif evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and not evaluation_round.evaluation_started:
            evaluation_round.time_label = "진행 중 · 평가 시작 전"
        elif evaluation_round.status == EvaluationRound.Status.IN_PROGRESS:
            delta = evaluation_round.end_at - now
            hours = max(0, int(delta.total_seconds() // 3600))
            evaluation_round.time_label = f"평가 중 · 마감 {hours}시간 전" if hours < 48 else f"평가 중 · 마감 {max(0, delta.days)}일 전"
        else:
            evaluation_round.time_label = "종료됨"

    available_rounds = EvaluationRound.objects.filter(
        Q(status=EvaluationRound.Status.SCHEDULED)
        | Q(status=EvaluationRound.Status.IN_PROGRESS, evaluation_started=False)
    ).order_by("-start_at")
    stats = {
        "total": len(rounds),
        "active": sum(r.status == EvaluationRound.Status.IN_PROGRESS for r in rounds),
        "ready": sum(
            r.ready_count == 4
            for r in rounds
            if r.status in {EvaluationRound.Status.SCHEDULED, EvaluationRound.Status.IN_PROGRESS}
            and not r.evaluation_started
        ),
        "missing_assignment": sum(not r.assignment_obj for r in rounds),
    }
    selected_round = None
    selected_id = request.GET.get("round", "").strip()
    if selected_id.isdigit():
        selected_round = next((r for r in rounds if r.id == int(selected_id)), None)
    if selected_round is None:
        selected_round = next((r for r in rounds if r.status == EvaluationRound.Status.IN_PROGRESS), None) or (rounds[0] if rounds else None)

    return render(
        request,
        "admin_ui/operations.html",
        _base_context(
            rounds=rounds,
            selected_round=selected_round,
            available_rounds=available_rounds,
            stats=stats,
        ),
    )


@admin_required
def admin_attendance(request):
    _sync_round_statuses()
    rounds = list(EvaluationRound.objects.all().order_by("-start_at"))
    selected_id = request.GET.get("round", "").strip()
    selected_round = None
    if selected_id.isdigit():
        selected_round = next((r for r in rounds if r.id == int(selected_id)), None)
    if selected_round is None:
        selected_round = next((r for r in rounds if r.status == EvaluationRound.Status.IN_PROGRESS), None) or (rounds[0] if rounds else None)

    if request.method == "POST":
        round_id = request.POST.get("round_id", "").strip()
        evaluation_round = get_object_or_404(EvaluationRound, pk=round_id)
        action = request.POST.get("action", "save")
        students = list(
            Student.objects.filter(is_active=True, user__is_active=True)
            .select_related("user")
            .order_by("user__first_name", "user__username")
        )
        if action == "mark_all_present":
            for student in students:
                RoundAttendance.objects.update_or_create(
                    evaluation_round=evaluation_round,
                    student=student,
                    defaults={"status": RoundAttendance.Status.PRESENT, "note": ""},
                )
            messages.success(request, f"{evaluation_round.name} 전체 학생을 출석으로 처리했습니다.")
        else:
            valid_statuses = set(RoundAttendance.Status.values)
            updated = 0
            for student in students:
                status = request.POST.get(f"status_{student.id}", RoundAttendance.Status.PRESENT)
                if status not in valid_statuses:
                    status = RoundAttendance.Status.PRESENT
                note = request.POST.get(f"note_{student.id}", "").strip()[:250]
                RoundAttendance.objects.update_or_create(
                    evaluation_round=evaluation_round,
                    student=student,
                    defaults={"status": status, "note": note},
                )
                updated += 1
            messages.success(request, f"{evaluation_round.name} 출결 {updated}명을 저장했습니다.")
        return redirect(f"/management/attendance/?round={evaluation_round.id}")

    rows = []
    stats = {"present": 0, "absent": 0, "excused": 0, "total": 0}
    if selected_round:
        students = list(
            Student.objects.filter(is_active=True, user__is_active=True)
            .select_related("user")
            .order_by("user__first_name", "user__username")
        )
        attendance_map = {
            item.student_id: item
            for item in RoundAttendance.objects.filter(evaluation_round=selected_round)
        }
        membership_map = {
            item.student_id: item
            for item in TeamMembership.objects.filter(team__evaluation_round=selected_round).select_related("team")
        }
        for student in students:
            attendance = attendance_map.get(student.id)
            status = attendance.status if attendance else RoundAttendance.Status.PRESENT
            membership = membership_map.get(student.id)
            rows.append({
                "student": student,
                "team": membership.team if membership else None,
                "status": status,
                "note": attendance.note if attendance else "",
                "team_eval_allowed": status == RoundAttendance.Status.PRESENT,
                "personal_eval_allowed": True,
            })
            stats[status] += 1
        stats["total"] = len(rows)

    return render(
        request,
        "admin_ui/attendance.html",
        _base_context(
            rounds=rounds,
            selected_round=selected_round,
            rows=rows,
            stats=stats,
            attendance_choices=RoundAttendance.Status.choices,
        ),
    )
