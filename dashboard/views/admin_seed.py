from django.contrib import messages
from django.shortcuts import get_object_or_404, render

from dashboard.models import EvaluationRound
from dashboard.services.seed_management_service import (
    apply_seed_weights,
    build_seed_management_context,
    parse_seed_weights,
)
from .common import _base_context, _redirect_back, _selected_round, admin_required


@admin_required
def admin_seed_management(request):
    rounds = EvaluationRound.objects.all().order_by("-start_at")
    selected_round = _selected_round(request, rounds)

    if request.method == "POST":
        weight_round = get_object_or_404(EvaluationRound, id=request.POST.get("weight_round_id"))
        values, error = parse_seed_weights(
            request.POST.get("seed_weight", 100),
            request.POST.get("seed_team_weight", 40),
            request.POST.get("seed_personal_weight", 60),
        )
        if error:
            messages.error(request, error)
            return _redirect_back(request, "admin_seed_management")

        apply_seed_weights(weight_round, values)
        messages.success(
            request,
            f"{weight_round.name}: 회차 {values['seed_weight']}% · 팀 {values['seed_team_weight']}% · 개인 {values['seed_personal_weight']}%로 저장했습니다.",
        )
        return _redirect_back(request, "admin_seed_management")

    context = build_seed_management_context(selected_round, request.GET.get("page"))
    return render(
        request,
        "admin_ui/seed_management.html",
        _base_context(rounds=rounds, selected_round=selected_round, **context),
    )
