from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .common import _base_context, _sync_round_statuses, admin_required
from ..models import (
    Assignment,
    EvaluationCriterion,
    EvaluationRound,
    EvaluationTemplate,
    Student,
    StudentAssignmentSubmission,
    Team,
    TeamAssignmentSubmission,
)


@admin_required
def admin_round_detail(request, round_id):
    """회차 하나를 중심으로 과제, 팀 배정, 제출물, 관리자 코멘트를 통합 조회한다."""
    _sync_round_statuses()
    evaluation_round = get_object_or_404(EvaluationRound, pk=round_id)
    assignments = list(
        Assignment.objects.filter(evaluation_round=evaluation_round)
        .prefetch_related("required_skills__skill")
        .order_by("assignment_type", "id")
    )
    for item in assignments:
        item.skill_items = list(item.required_skills.all())
    team_assignment = next((item for item in assignments if item.assignment_type == Assignment.AssignmentType.TEAM), None)
    individual_assignment = next((item for item in assignments if item.assignment_type == Assignment.AssignmentType.INDIVIDUAL), None)
    assignment = team_assignment or individual_assignment

    teams = list(
        Team.objects.filter(evaluation_round=evaluation_round, is_active=True)
        .prefetch_related("memberships__student__user")
        .order_by("name")
    )
    submissions = {}
    if team_assignment:
        submissions = {
            item.team_id: item
            for item in TeamAssignmentSubmission.objects.filter(assignment=team_assignment)
            .select_related("team", "submitted_by__user", "commented_by")
        }

    individual_submissions = {}
    if individual_assignment:
        individual_submissions = {
            item.student_id: item
            for item in StudentAssignmentSubmission.objects.filter(assignment=individual_assignment)
            .select_related("student__user")
        }

    team_rows = []
    assigned_student_ids = set()
    for team in teams:
        memberships = list(team.memberships.all())
        memberships.sort(key=lambda m: (not m.is_leader, m.student.name))
        assigned_student_ids.update(m.student_id for m in memberships)
        team_rows.append({
            "team": team,
            "memberships": memberships,
            "submission": submissions.get(team.id),
        })

    active_students = list(
        Student.objects.filter(is_active=True, user__is_active=True)
        .select_related("user")
        .order_by("user__first_name", "user__username")
    )
    active_student_count = len(active_students)
    individual_rows = [
        {"student": student, "submission": individual_submissions.get(student.id)}
        for student in active_students
    ]
    team_template_count = evaluation_round.evaluation_templates.filter(
        is_active=True, evaluation_type=EvaluationTemplate.EvaluationType.TEAM
    ).count()
    personal_template_count = evaluation_round.evaluation_templates.filter(
        is_active=True, evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL
    ).count()
    team_submitted_count = len(submissions)
    individual_submitted_count = len(individual_submissions)
    stats = {
        "teams": len(teams),
        "assigned": len(assigned_student_ids),
        "unassigned": max(active_student_count - len(assigned_student_ids), 0),
        "team_submitted": team_submitted_count,
        "team_missing": max(len(teams) - team_submitted_count, 0) if team_assignment else 0,
        "individual_submitted": individual_submitted_count,
        "individual_missing": max(active_student_count - individual_submitted_count, 0) if individual_assignment else 0,
    }
    ready_checks = {
        "assignment": bool(assignments),
        "teams": bool(teams),
        "team_template": team_template_count > 0,
        "personal_template": personal_template_count > 0,
    }
    ready_percent = int(sum(ready_checks.values()) / 4 * 100)
    can_round_start = evaluation_round.status == EvaluationRound.Status.SCHEDULED
    can_assignment_manage = evaluation_round.status in {EvaluationRound.Status.SCHEDULED, EvaluationRound.Status.IN_PROGRESS} and not evaluation_round.evaluation_started
    can_evaluation_start = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and not evaluation_round.evaluation_started and ready_percent == 100
    can_pause = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started and not evaluation_round.is_locked
    can_resume = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started and evaluation_round.is_locked
    can_end = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started
    can_template_apply = evaluation_round.status != EvaluationRound.Status.ENDED and not evaluation_round.evaluation_started

    team_template_options = list(
        EvaluationTemplate.objects.filter(
            is_active=True,
            evaluation_round__isnull=True,
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
        ).prefetch_related("criteria").order_by("name", "id")
    )
    personal_template_options = list(
        EvaluationTemplate.objects.filter(
            is_active=True,
            evaluation_round__isnull=True,
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
        ).prefetch_related("criteria").order_by("name", "id")
    )
    applied_team_template = evaluation_round.evaluation_templates.filter(
        is_active=True, evaluation_type=EvaluationTemplate.EvaluationType.TEAM
    ).first()
    applied_personal_template = evaluation_round.evaluation_templates.filter(
        is_active=True, evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL
    ).first()

    return render(request, "admin_ui/round_detail.html", _base_context(
        evaluation_round=evaluation_round, assignment=assignment, assignments=assignments, team_assignment=team_assignment,
        individual_assignment=individual_assignment, team_rows=team_rows, individual_rows=individual_rows,
        stats=stats, ready_checks=ready_checks, ready_percent=ready_percent,
        team_template_count=team_template_count, personal_template_count=personal_template_count,
        can_round_start=can_round_start, can_assignment_manage=can_assignment_manage,
        can_evaluation_start=can_evaluation_start, can_pause=can_pause, can_resume=can_resume, can_end=can_end,
        can_template_apply=can_template_apply, team_template_options=team_template_options,
        personal_template_options=personal_template_options,
        applied_team_template=applied_team_template, applied_personal_template=applied_personal_template,
    ))


@admin_required
@require_POST
@transaction.atomic
def admin_round_apply_templates(request, round_id):
    """기존 평가 템플릿을 선택한 회차 전용 템플릿으로 복사 적용한다."""
    evaluation_round = get_object_or_404(EvaluationRound, pk=round_id)
    if evaluation_round.status == EvaluationRound.Status.ENDED or evaluation_round.evaluation_started:
        messages.error(request, "평가가 시작되었거나 종료된 회차의 템플릿은 변경할 수 없습니다.")
        return redirect("admin_round_detail", round_id=evaluation_round.id)

    selections = [
        ("team_template_id", EvaluationTemplate.EvaluationType.TEAM, "팀 평가"),
        ("personal_template_id", EvaluationTemplate.EvaluationType.PERSONAL, "개인 평가"),
    ]
    applied = []

    for field_name, evaluation_type, label in selections:
        raw_id = request.POST.get(field_name, "").strip()
        if not raw_id:
            continue
        source = get_object_or_404(
            EvaluationTemplate.objects.prefetch_related("criteria"),
            pk=raw_id,
            evaluation_type=evaluation_type,
            evaluation_round__isnull=True,
            is_active=True,
        )
        source_name = source.name
        criterion_rows = [
            {
                "title": criterion.title,
                "description": criterion.description,
                "order": criterion.order,
                "max_score": criterion.max_score,
                "is_required": criterion.is_required,
            }
            for criterion in source.criteria.all().order_by("order", "id")
        ]

        EvaluationTemplate.objects.filter(
            evaluation_round=evaluation_round,
            evaluation_type=evaluation_type,
        ).delete()

        copied = EvaluationTemplate.objects.create(
            name=source_name,
            evaluation_type=evaluation_type,
            evaluation_round=evaluation_round,
            is_active=True,
        )
        EvaluationCriterion.objects.bulk_create([
            EvaluationCriterion(template=copied, **row) for row in criterion_rows
        ])
        applied.append(label)

    if applied:
        messages.success(request, f"{', '.join(applied)} 템플릿을 이 회차에 적용했습니다.")
    else:
        messages.warning(request, "적용할 템플릿을 하나 이상 선택해 주세요.")
    return redirect("admin_round_detail", round_id=evaluation_round.id)


@admin_required
@require_POST
def admin_submission_comment(request, submission_id):
    submission = get_object_or_404(
        TeamAssignmentSubmission.objects.select_related("assignment__evaluation_round", "team"),
        pk=submission_id,
    )
    submission.admin_comment = request.POST.get("admin_comment", "").strip()
    submission.commented_by = request.user if submission.admin_comment else None
    submission.commented_at = timezone.now() if submission.admin_comment else None
    submission.save(update_fields=["admin_comment", "commented_by", "commented_at", "updated_at"])
    if submission.admin_comment:
        messages.success(request, f"{submission.team.name} 제출물에 관리자 코멘트를 저장했습니다.")
    else:
        messages.success(request, f"{submission.team.name} 제출물의 관리자 코멘트를 삭제했습니다.")
    return redirect("admin_round_detail", round_id=submission.assignment.evaluation_round_id)


@admin_required
def admin_rounds(request):
    _sync_round_statuses()
    rounds = list(EvaluationRound.objects.all())
    for evaluation_round in rounds:
        evaluation_round.status_display = evaluation_round.get_status_display()
        evaluation_round.assignment_title = " / ".join(evaluation_round.assignments.values_list("title", flat=True))
        evaluation_round.can_edit = evaluation_round.status == EvaluationRound.Status.SCHEDULED
        evaluation_round.can_delete = True
        evaluation_round.can_round_start = evaluation_round.status == EvaluationRound.Status.SCHEDULED
        evaluation_round.can_evaluation_start = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and not evaluation_round.evaluation_started
        evaluation_round.can_end = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started
        evaluation_round.can_reopen = evaluation_round.status == EvaluationRound.Status.ENDED
        evaluation_round.can_lock = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started and not evaluation_round.is_locked
        evaluation_round.can_unlock = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started and evaluation_round.is_locked
        evaluation_round.is_selected_current = evaluation_round.is_current

    current_round = next((r for r in rounds if r.is_current), None)
    stats = {
        "total": len(rounds),
        "scheduled": sum(r.status == EvaluationRound.Status.SCHEDULED for r in rounds),
        "active": sum(r.status == EvaluationRound.Status.IN_PROGRESS for r in rounds),
        "ended": sum(r.status == EvaluationRound.Status.ENDED for r in rounds),
    }
    return render(request, "admin_ui/rounds.html", _base_context(rounds=rounds, stats=stats, current_round=current_round))
