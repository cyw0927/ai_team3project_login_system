from .common import *
from ..services.missing_evaluations_service import build_missing_evaluations_data


@admin_required
def admin_missing_evaluations(request):
    """회차별 미제출 팀/개인 평가를 평가자-대상 단위로 보여준다."""
    rounds = EvaluationRound.objects.all().order_by("-start_at")
    selected_round = _selected_round(request, rounds)
    evaluation_type = request.GET.get("type", "all")
    query = request.GET.get("q", "").strip()

    data = build_missing_evaluations_data(
        selected_round,
        evaluation_type,
        query,
        complete_team_evaluator_ids=_complete_team_evaluator_ids,
        complete_personal_evaluator_ids=_complete_personal_evaluator_ids,
    )

    return render(
        request,
        "admin_ui/missing_evaluations.html",
        _base_context(
            rounds=rounds,
            selected_round=selected_round,
            rows=data["rows"],
            summary=data["summary"],
            evaluation_type=evaluation_type,
            query=query,
        ),
    )
