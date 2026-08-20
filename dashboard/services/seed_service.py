"""Seed calculation helpers for automatic team assignment."""

from decimal import Decimal

from dashboard.models import EvaluationRound, StudentResult


def cumulative_seed_scores_before(evaluation_round):
    """Return weighted cumulative Seed scores from ended rounds before the target round."""
    previous_results = (
        StudentResult.objects.filter(
            evaluation_round__start_at__lt=evaluation_round.start_at,
            evaluation_round__status=EvaluationRound.Status.ENDED,
            is_excluded=False,
        )
        .exclude(final_score__isnull=True)
        .select_related("evaluation_round")
        .order_by("evaluation_round__start_at", "student_id")
    )

    weighted_totals = {}
    weight_totals = {}

    for result in previous_results:
        round_obj = result.evaluation_round
        history_weight = int(round_obj.seed_weight or 0)
        if history_weight <= 0:
            continue

        team_weight = int(round_obj.seed_team_weight or 0)
        personal_weight = int(round_obj.seed_personal_weight or 0)
        score_weight_total = team_weight + personal_weight
        if score_weight_total <= 0:
            continue

        seed_base_score = (
            (result.team_score * Decimal(team_weight))
            + (result.personal_score * Decimal(personal_weight))
        ) / Decimal(score_weight_total)

        weighted_totals[result.student_id] = (
            weighted_totals.get(result.student_id, Decimal("0"))
            + (seed_base_score * Decimal(history_weight))
        )
        weight_totals[result.student_id] = weight_totals.get(result.student_id, 0) + history_weight

    return {
        student_id: weighted_totals[student_id] / Decimal(weight_totals[student_id])
        for student_id in weighted_totals
        if weight_totals.get(student_id)
    }


def previous_round_for(evaluation_round):
    if not evaluation_round:
        return None
    return (
        EvaluationRound.objects
        .filter(start_at__lt=evaluation_round.start_at, student_results__isnull=False)
        .distinct()
        .order_by("-start_at", "-id")
        .first()
    )
