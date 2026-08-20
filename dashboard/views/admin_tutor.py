from django.contrib import messages
from django.db import transaction
from django.db.models import Avg
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .common import _base_context, _current_round, admin_required
from ..forms import EvaluationRoundForm
from ..models import (
    EvaluationRound,
    EvaluationTemplate,
    Student,
    Team,
    TeamEvaluation,
    TeamEvaluationScore,
)
from ..services.result_service import _recalculate_round_results
from ..services.scoring_policy import (
    DEFAULT_PERSONAL_WEIGHT,
    DEFAULT_TEAM_WEIGHT,
    DEFAULT_TUTOR_WEIGHT,
    tutor_weight_for,
    validate_score_weights,
)


def _selected_round(request):
    rounds = EvaluationRound.objects.all().order_by("-start_at")
    round_id = request.POST.get("round_id") or request.GET.get("round")
    selected = rounds.filter(pk=round_id).first() if round_id else _current_round()
    return rounds, selected


def _tutor_profile(user):
    """Temporary compatibility bridge until tutor evaluations get a dedicated model."""
    profile, created = Student.objects.get_or_create(
        user=user,
        defaults={"is_active": False, "affiliation": "튜터"},
    )
    if created:
        return profile
    return profile


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
    teams = []
    criteria = []
    rows = []
    completed_count = 0
    can_edit = False
    tutor_weight = 0

    if selected_round:
        tutor_weight = tutor_weight_for(selected_round)
        teams = list(
            Team.objects.filter(evaluation_round=selected_round, is_active=True).order_by("name")
        )
        template = (
            EvaluationTemplate.objects.filter(
                evaluation_round=selected_round,
                evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
                is_active=True,
            )
            .prefetch_related("criteria")
            .first()
        )
        criteria = list(template.criteria.all().order_by("order", "id")) if template else []
        can_edit = (
            selected_round.status == EvaluationRound.Status.IN_PROGRESS
            and selected_round.evaluation_started
            and not selected_round.is_locked
        )

        tutor = _tutor_profile(request.user)

        if request.method == "POST":
            if not can_edit:
                messages.error(request, "평가가 진행 중이고 잠금 해제된 상태에서만 튜터 평가를 저장할 수 있습니다.")
                return redirect(f"/management/tutor-evaluations/?round={selected_round.id}")
            if not criteria:
                messages.error(request, "이 회차에 적용된 팀 평가 문항이 없습니다.")
                return redirect(f"/management/tutor-evaluations/?round={selected_round.id}")

            team = get_object_or_404(
                Team,
                pk=request.POST.get("team_id"),
                evaluation_round=selected_round,
                is_active=True,
            )
            score_values = {}
            for criterion in criteria:
                raw = (request.POST.get(f"score_{criterion.id}") or "").strip()
                try:
                    score = int(raw)
                except ValueError:
                    score = 0
                if score < 1 or score > criterion.max_score:
                    messages.error(
                        request,
                        f"{criterion.title}: 1~{criterion.max_score}점 사이로 입력해 주세요.",
                    )
                    return redirect(f"/management/tutor-evaluations/?round={selected_round.id}#team-{team.id}")
                score_values[criterion.id] = score

            evaluation, _ = TeamEvaluation.objects.get_or_create(
                evaluation_round=selected_round,
                evaluator=tutor,
                target_team=team,
            )
            evaluation.comment = (request.POST.get("comment") or "").strip()
            evaluation.is_submitted = True
            evaluation.submitted_at = timezone.now()
            evaluation.save(update_fields=["comment", "is_submitted", "submitted_at", "updated_at"])

            for criterion in criteria:
                TeamEvaluationScore.objects.update_or_create(
                    evaluation=evaluation,
                    criterion=criterion,
                    defaults={"score": score_values[criterion.id]},
                )

            _recalculate_round_results(selected_round)
            messages.success(request, f"{team.name} 튜터 평가와 코멘트를 저장했습니다.")
            return redirect(f"/management/tutor-evaluations/?round={selected_round.id}#team-{team.id}")

        own_evaluations = {
            evaluation.target_team_id: evaluation
            for evaluation in TeamEvaluation.objects.filter(
                evaluation_round=selected_round,
                evaluator=tutor,
            ).prefetch_related("scores")
        }
        completed_count = sum(1 for evaluation in own_evaluations.values() if evaluation.is_submitted)

        all_tutor_averages = dict(
            TeamEvaluationScore.objects.filter(
                evaluation__evaluation_round=selected_round,
                evaluation__is_submitted=True,
                evaluation__evaluator__user__is_staff=True,
            )
            .values("evaluation__target_team_id")
            .annotate(avg=Avg("score"))
            .values_list("evaluation__target_team_id", "avg")
        )

        for team in teams:
            evaluation = own_evaluations.get(team.id)
            score_map = {
                item.criterion_id: item.score
                for item in evaluation.scores.all()
            } if evaluation else {}
            rows.append({
                "team": team,
                "evaluation": evaluation,
                "criterion_rows": [
                    {"criterion": criterion, "value": score_map.get(criterion.id)}
                    for criterion in criteria
                ],
                "team_tutor_average": all_tutor_averages.get(team.id),
            })

    return render(
        request,
        "admin_ui/tutor_evaluations.html",
        _base_context(
            rounds=rounds,
            selected_round=selected_round,
            criteria=criteria,
            tutor_rows=rows,
            completed_count=completed_count,
            team_count=len(teams),
            can_edit=can_edit,
            tutor_weight=tutor_weight,
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

    _recalculate_round_results(round_obj)
    messages.success(
        request,
        f"가중치를 팀 {values['team_weight']}% / 개인 {values['personal_weight']}% / "
        f"튜터 {values['tutor_weight']}%로 저장하고 재계산했습니다.",
    )
    return redirect(request.POST.get("next") or "admin_evaluation_results")
