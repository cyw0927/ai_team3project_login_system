"""Student evaluation submission and status views.

Evaluation submission calls the result service directly, so these routes no
longer depend on legacy result-calculation symbols exported from views.common.
"""

from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.shortcuts import redirect, render
from django.utils import timezone

from .common import (
    _attendance_for,
    _base_context,
    _criteria_complete,
    _current_round_for_evaluation,
    _save_scores,
    _student_progress,
    _student_team,
    _template_for,
    student_required,
)
from ..models import (
    EvaluationRound,
    EvaluationTemplate,
    PersonalEvaluation,
    PersonalEvaluationScore,
    RoundAttendance,
    Student,
    Team,
    TeamEvaluation,
    TeamEvaluationScore,
)
from ..services.result_service import recalculate_round_results


@student_required
@transaction.atomic
def student_team_evaluation(request):
    evaluation_round = _current_round_for_evaluation()
    if not evaluation_round:
        return render(
            request,
            "student/team_evaluation.html",
            _base_context(evaluation_open=False, evaluation_locked=False, target_teams=[], criteria=[]),
        )
    if evaluation_round.is_locked:
        if request.method == "POST":
            messages.error(request, "관리자가 현재 평가를 일시 중단했습니다. 평가 재개 후 다시 제출해 주세요.")
        return render(
            request,
            "student/team_evaluation.html",
            _base_context(
                evaluation_open=False,
                evaluation_locked=True,
                evaluation_round=evaluation_round,
                target_teams=[],
                criteria=[],
            ),
        )

    attendance = _attendance_for(request.student, evaluation_round)
    if attendance and attendance.status in {RoundAttendance.Status.ABSENT, RoundAttendance.Status.EXCUSED}:
        if request.method == "POST":
            messages.error(request, "발표 당일 결석/공결 처리되어 다른 팀 평가는 제출할 수 없습니다.")
        return render(
            request,
            "student/team_evaluation.html",
            _base_context(
                evaluation_open=False,
                attendance_blocked=True,
                attendance=attendance,
                evaluation_round=evaluation_round,
                target_teams=[],
                criteria=[],
            ),
        )

    my_team = _student_team(request.student, evaluation_round)
    template = _template_for(evaluation_round, EvaluationTemplate.EvaluationType.TEAM)
    criteria = list(template.criteria.all().order_by("order", "id")) if template else []
    target_teams = list(
        Team.objects.filter(evaluation_round=evaluation_round, is_active=True)
        .exclude(pk=getattr(my_team, "pk", None))
        .annotate(member_count=Count("memberships"))
        .order_by("name")
    )

    existing = {
        evaluation.target_team_id: evaluation
        for evaluation in TeamEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            evaluator=request.student,
            target_team__in=target_teams,
        ).prefetch_related("scores")
    }
    for team in target_teams:
        evaluation = existing.get(team.id)
        team.is_submitted = bool(evaluation and evaluation.is_submitted)
        team.is_draft = bool(evaluation and not evaluation.is_submitted and evaluation.scores.exists())

    selected_team_id = request.POST.get("target_team_id") or request.GET.get("team")
    selected_team = next((team for team in target_teams if str(team.id) == str(selected_team_id)), None)
    saved_scores = {}
    saved_comment = ""

    if request.method == "POST":
        if not selected_team:
            messages.error(request, "평가할 팀을 선택하세요.")
        elif not criteria:
            messages.error(request, "등록된 팀 평가 항목이 없습니다.")
        else:
            action = request.POST.get("action", "draft")
            if action == "submit" and not _criteria_complete(request.POST, criteria):
                messages.error(request, "필수 평가 항목을 모두 입력해야 최종 제출할 수 있습니다.")
            else:
                evaluation, _ = TeamEvaluation.objects.get_or_create(
                    evaluation_round=evaluation_round,
                    evaluator=request.student,
                    target_team=selected_team,
                )
                evaluation.comment = request.POST.get("comment", "").strip()
                evaluation.is_submitted = action == "submit"
                evaluation.submitted_at = timezone.now() if evaluation.is_submitted else None
                evaluation.save()
                _save_scores(evaluation, TeamEvaluationScore, criteria, request.POST)
                if evaluation.is_submitted:
                    recalculate_round_results(evaluation_round)
                    messages.success(
                        request,
                        f"{selected_team.name} 평가를 최종 제출했습니다. 평가 종료 전에는 다시 수정할 수 있습니다.",
                    )
                else:
                    messages.success(request, f"{selected_team.name} 평가를 임시 저장했습니다.")
                return redirect(f"/team-evaluation/?team={selected_team.id}")

    if selected_team:
        evaluation = existing.get(selected_team.id) or TeamEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            evaluator=request.student,
            target_team=selected_team,
        ).first()
        if evaluation:
            saved_scores = {score.criterion_id: score.score for score in evaluation.scores.all()}
            saved_comment = evaluation.comment

    submitted_count = sum(1 for team in target_teams if team.is_submitted)
    draft_count = sum(1 for team in target_teams if team.is_draft)
    remaining_count = max(len(target_teams) - submitted_count, 0)
    next_team = next(
        (
            team
            for team in target_teams
            if not team.is_submitted and (not selected_team or team.id != selected_team.id)
        ),
        None,
    )
    selected_position = next(
        (
            index
            for index, team in enumerate(target_teams, start=1)
            if selected_team and team.id == selected_team.id
        ),
        None,
    )
    selected_evaluation = existing.get(selected_team.id) if selected_team else None
    return render(
        request,
        "student/team_evaluation.html",
        _base_context(
            evaluation_open=True,
            evaluation_round=evaluation_round,
            my_team=my_team,
            target_teams=target_teams,
            criteria=criteria,
            selected_team=selected_team,
            saved_scores=saved_scores,
            saved_comment=saved_comment,
            submitted_count=submitted_count,
            draft_count=draft_count,
            remaining_count=remaining_count,
            total_count=len(target_teams),
            next_team=next_team,
            selected_position=selected_position,
            selected_evaluation=selected_evaluation,
        ),
    )


@student_required
@transaction.atomic
def student_personal_evaluation(request):
    evaluation_round = _current_round_for_evaluation()
    if not evaluation_round:
        return render(
            request,
            "student/personal_evaluation.html",
            _base_context(evaluation_open=False, evaluation_locked=False, target_members=[], criteria=[]),
        )
    if evaluation_round.is_locked:
        if request.method == "POST":
            messages.error(request, "관리자가 현재 평가를 일시 중단했습니다. 평가 재개 후 다시 제출해 주세요.")
        return render(
            request,
            "student/personal_evaluation.html",
            _base_context(
                evaluation_open=False,
                evaluation_locked=True,
                evaluation_round=evaluation_round,
                target_members=[],
                criteria=[],
            ),
        )

    my_team = _student_team(request.student, evaluation_round)
    if not my_team:
        return render(
            request,
            "student/personal_evaluation.html",
            _base_context(evaluation_open=False, no_team=True, target_members=[], criteria=[]),
        )

    attendance = _attendance_for(request.student, evaluation_round)
    absent_from_team_eval = bool(
        attendance
        and attendance.status in {RoundAttendance.Status.ABSENT, RoundAttendance.Status.EXCUSED}
    )
    target_team_count = 0 if absent_from_team_eval else Team.objects.filter(
        evaluation_round=evaluation_round,
        is_active=True,
    ).exclude(pk=my_team.pk).count()
    submitted_team_count = TeamEvaluation.objects.filter(
        evaluation_round=evaluation_round,
        evaluator=request.student,
        is_submitted=True,
    ).count()
    team_evaluation_complete = (
        absent_from_team_eval
        or target_team_count == 0
        or submitted_team_count >= target_team_count
    )

    template = _template_for(evaluation_round, EvaluationTemplate.EvaluationType.PERSONAL)
    criteria = list(template.criteria.all().order_by("order", "id")) if template else []
    target_members = list(
        Student.objects.filter(
            team_memberships__team=my_team,
            is_active=True,
            user__is_active=True,
        )
        .exclude(pk=request.student.pk)
        .select_related("user")
        .distinct()
        .order_by("user__first_name", "user__username")
    )

    existing = {
        evaluation.target_student_id: evaluation
        for evaluation in PersonalEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            evaluator=request.student,
            target_student__in=target_members,
        ).prefetch_related("scores")
    }
    for member in target_members:
        evaluation = existing.get(member.id)
        member.is_submitted = bool(evaluation and evaluation.is_submitted)
        member.is_draft = bool(
            evaluation
            and not evaluation.is_submitted
            and (evaluation.scores.exists() or evaluation.comment)
        )

    selected_member_id = request.POST.get("target_student_id") or request.GET.get("member")
    selected_member = next(
        (member for member in target_members if str(member.id) == str(selected_member_id)),
        None,
    )
    saved_scores = {}
    saved_comment = ""

    if request.method == "POST":
        if not team_evaluation_complete:
            messages.error(request, "모든 다른 팀의 팀 평가를 먼저 최종 제출해야 개인 평가를 할 수 있습니다.")
        elif not selected_member:
            messages.error(request, "평가할 팀원을 선택하세요.")
        elif not criteria:
            messages.error(request, "등록된 개인 평가 항목이 없습니다.")
        else:
            action = request.POST.get("action", "draft")
            invalid_personal_score = False
            for criterion in criteria:
                raw_score = request.POST.get(f"criterion_{criterion.id}")
                if not raw_score:
                    continue
                try:
                    score = int(raw_score)
                except (TypeError, ValueError):
                    invalid_personal_score = True
                    break
                if score not in {1, 2, 3, 4, 5}:
                    invalid_personal_score = True
                    break

            if action == "submit" and not _criteria_complete(request.POST, criteria):
                messages.error(request, "필수 평가 항목을 모두 입력해야 최종 제출할 수 있습니다.")
            elif invalid_personal_score:
                messages.error(request, "개인 평가 점수는 1점부터 5점까지만 사용할 수 있습니다.")
            else:
                evaluation, _ = PersonalEvaluation.objects.get_or_create(
                    evaluation_round=evaluation_round,
                    evaluator=request.student,
                    target_student=selected_member,
                )
                evaluation.comment = request.POST.get("comment", "").strip()
                evaluation.is_submitted = action == "submit"
                evaluation.submitted_at = timezone.now() if evaluation.is_submitted else None
                evaluation.save()
                _save_scores(evaluation, PersonalEvaluationScore, criteria, request.POST)
                if evaluation.is_submitted:
                    recalculate_round_results(evaluation_round)
                    messages.success(
                        request,
                        f"{selected_member.name} 평가를 최종 제출했습니다. 평가 종료 전에는 다시 수정할 수 있습니다.",
                    )
                else:
                    messages.success(request, f"{selected_member.name} 평가를 임시 저장했습니다.")
                return redirect(f"/personal-evaluation/?member={selected_member.id}")

    if selected_member:
        evaluation = existing.get(selected_member.id) or PersonalEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            evaluator=request.student,
            target_student=selected_member,
        ).first()
        if evaluation:
            saved_scores = {score.criterion_id: score.score for score in evaluation.scores.all()}
            saved_comment = evaluation.comment

    submitted_count = sum(1 for member in target_members if member.is_submitted)
    draft_count = sum(1 for member in target_members if member.is_draft)
    remaining_count = max(len(target_members) - submitted_count, 0)
    next_member = next(
        (
            member
            for member in target_members
            if not member.is_submitted and (not selected_member or member.id != selected_member.id)
        ),
        None,
    )
    selected_position = next(
        (
            index
            for index, member in enumerate(target_members, start=1)
            if selected_member and member.id == selected_member.id
        ),
        None,
    )
    selected_evaluation = existing.get(selected_member.id) if selected_member else None

    return render(
        request,
        "student/personal_evaluation.html",
        _base_context(
            evaluation_open=True,
            evaluation_round=evaluation_round,
            my_team=my_team,
            team_evaluation_complete=team_evaluation_complete,
            submitted_team_count=submitted_team_count,
            target_team_count=target_team_count,
            target_members=target_members,
            criteria=criteria,
            selected_member=selected_member,
            saved_scores=saved_scores,
            saved_comment=saved_comment,
            submitted_count=submitted_count,
            draft_count=draft_count,
            remaining_count=remaining_count,
            total_count=len(target_members),
            next_member=next_member,
            selected_position=selected_position,
            selected_evaluation=selected_evaluation,
            attendance=attendance,
            absent_from_team_eval=absent_from_team_eval,
        ),
    )


@student_required
def student_evaluation_status(request):
    evaluation_round = _current_round_for_evaluation() or EvaluationRound.objects.order_by("-start_at").first()
    if not evaluation_round:
        return render(
            request,
            "student/evaluation_status.html",
            _base_context(
                evaluation_round=None,
                team_statuses=[],
                personal_statuses=[],
                progress=_student_progress(request.student, None, None),
            ),
        )

    evaluation_round.status_display = evaluation_round.get_status_display()
    my_team = _student_team(request.student, evaluation_round)
    attendance = _attendance_for(request.student, evaluation_round)
    absent_from_team_eval = bool(
        attendance
        and attendance.status in {RoundAttendance.Status.ABSENT, RoundAttendance.Status.EXCUSED}
    )
    target_teams = [] if absent_from_team_eval else (
        list(
            Team.objects.filter(evaluation_round=evaluation_round, is_active=True)
            .exclude(pk=getattr(my_team, "pk", None))
            .annotate(member_count=Count("memberships"))
            .order_by("name")
        ) if my_team else []
    )
    team_eval_map = {
        evaluation.target_team_id: evaluation
        for evaluation in TeamEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            evaluator=request.student,
        )
    }
    team_statuses = []
    for team in target_teams:
        evaluation = team_eval_map.get(team.id)
        if evaluation and evaluation.is_submitted:
            status_display = "제출 완료"
        elif evaluation:
            status_display = "임시 저장"
        else:
            status_display = "미평가"
        team_statuses.append({
            "team_name": team.name,
            "project_title": team.project_title or "-",
            "status_display": status_display,
            "submitted": bool(evaluation and evaluation.is_submitted),
            "updated_at": evaluation.updated_at if evaluation else None,
        })

    target_members = []
    if my_team:
        target_members = list(
            Student.objects.filter(team_memberships__team=my_team)
            .exclude(pk=request.student.pk)
            .select_related("user")
            .distinct()
        )
    personal_eval_map = {
        evaluation.target_student_id: evaluation
        for evaluation in PersonalEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            evaluator=request.student,
        )
    }
    personal_statuses = []
    for member in target_members:
        evaluation = personal_eval_map.get(member.id)
        personal_statuses.append({
            "student_name": member.name,
            "status_display": "제출 완료" if evaluation and evaluation.is_submitted else "미평가",
            "submitted": bool(evaluation and evaluation.is_submitted),
            "updated_at": evaluation.updated_at if evaluation else None,
        })

    progress = _student_progress(request.student, evaluation_round, my_team)
    return render(
        request,
        "student/evaluation_status.html",
        _base_context(
            evaluation_round=evaluation_round,
            my_team=my_team,
            team_statuses=team_statuses,
            personal_statuses=personal_statuses,
            progress=progress,
        ),
    )
