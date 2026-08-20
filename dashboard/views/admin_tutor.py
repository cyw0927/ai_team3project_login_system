from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .common import _base_context, _current_round, admin_required
from ..forms import EvaluationRoundForm
from ..models import EvaluationRound
from ..services.result_service import recalculate_round_results
from ..services.scoring_policy import (
    DEFAULT_PERSONAL_WEIGHT,
    DEFAULT_TEAM_WEIGHT,
    DEFAULT_TUTOR_WEIGHT,
    validate_score_weights,
)
from ..services.tutor_evaluation_service import (
    build_tutor_evaluation_state,
    save_tutor_team_evaluation,
)


def _selected_round(request):
    rounds = EvaluationRound.objects.all().order_by("-start_at")
    round_id = request.POST.get("round_id") or request.GET.get("round")
    selected = rounds.filter(pk=round_id).first() if round_id else _current_round()
    return rounds, selected


@admin_required
@require_POST
@transaction.atomic
def admin_round_create(request):
    """Create new rounds with the default 40/30/30 scoring policy."""
    form = EvaluationRoundForm(request.POST)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect("admin_rounds")

    evaluation_round = form.save(commit=False)
    evaluation_round.status = EvaluationRound.Status.SCHEDULED
    evaluation_round.evaluation_started = False
    evaluation_round.team_weight = DEFAULT_TEAM_WEIGHT
    evaluation_round.personal_weight = DEFAULT_PERSONAL_WEIGHT
    evaluation_round.save()
    messages.success(
        request,
        f"{evaluation_round.name} 회차를 생성했습니다. 기본 가중치는 학생 팀 {DEFAULT_TEAM_WEIGHT}% / "
        f"동료 개인 {DEFAULT_PERSONAL_WEIGHT}% / 튜터 팀 {DEFAULT_TUTOR_WEIGHT}%입니다.",
    )
    return redirect("admin_rounds")


@admin_required
@transaction.atomic
def admin_tutor_evaluations(request):
    rounds, selected_round = _selected_round(request)
    state = None

    if selected_round:
        if request.method == "POST":
            try:
                team = save_tutor_team_evaluation(
                    selected_round,
                    request.user,
                    request.POST.get("team_id"),
                    request.POST,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect(f"/management/tutor-evaluations/?round={selected_round.id}")

            recalculate_round_results(selected_round)
            messages.success(request, f"{team.name} 튜터 평가와 코멘트를 저장했습니다.")
            return redirect(
                f"/management/tutor-evaluations/?round={selected_round.id}#team-{team.id}"
            )

        state = build_tutor_evaluation_state(selected_round, request.user)

    return render(
        request,
        "admin_ui/tutor_evaluations.html",
        _base_context(
            rounds=rounds,
            selected_round=selected_round,
            criteria=state.criteria if state else [],
            tutor_rows=state.rows if state else [],
            completed_count=state.completed_count if state else 0,
            team_count=len(state.teams) if state else 0,
            can_edit=state.can_edit if state else False,
            tutor_weight=state.tutor_weight if state else 0,
        ),
    )


@admin_required
@require_POST
@transaction.atomic
def admin_result_weights_save(request):
    round_obj = get_object_or_404(EvaluationRound, id=request.POST.get("round_id"))
    values, error = validate_score_weights(
        request.POST.get("team_weight", DEFAULT_TEAM_WEIGHT),
        request.POST.get("personal_weight", DEFAULT_PERSONAL_WEIGHT),
        request.POST.get("tutor_weight", DEFAULT_TUTOR_WEIGHT),
    )
    if error:
        messages.error(request, error)
        return redirect(request.POST.get("next") or "admin_evaluation_results")

    expected_tutor = 100 - values["team_weight"] - values["personal_weight"]
    if values["tutor_weight"] != expected_tutor:
        messages.error(request, "튜터 가중치는 100%에서 팀·개인 가중치를 뺀 값과 같아야 합니다.")
        return redirect(request.POST.get("next") or "admin_evaluation_results")

    round_obj.team_weight = values["team_weight"]
    round_obj.personal_weight = values["personal_weight"]
    round_obj.save(update_fields=["team_weight", "personal_weight", "updated_at"])

    recalculate_round_results(round_obj)
    messages.success(
        request,
        f"가중치를 팀 {values['team_weight']}% / 개인 {values['personal_weight']}% / "
        f"튜터 {values['tutor_weight']}%로 저장하고 재계산했습니다.",
    )
    return redirect(request.POST.get("next") or "admin_evaluation_results")
