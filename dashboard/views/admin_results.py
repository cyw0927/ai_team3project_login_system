from django.contrib import messages
from django.shortcuts import redirect, render

from .common import _base_context, admin_required
from ..services.evaluation_results_service import build_evaluation_results_context
from ..services.result_service import _recalculate_round_results
from ..services.scoring_policy import tutor_weight_for


@admin_required
def admin_evaluation_results(request):
    context = build_evaluation_results_context(request)
    selected_round = context["selected_round"]

    if selected_round:
        context["tutor_weight"] = tutor_weight_for(selected_round)

    if request.method == "POST" and selected_round:
        _recalculate_round_results(selected_round)
        tutor_weight = context["tutor_weight"]
        messages.success(
            request,
            f"평가 결과를 다시 계산했습니다. 학생 팀 {selected_round.team_weight}% + "
            f"동료 개인 {selected_round.personal_weight}% + 튜터 팀 {tutor_weight}% 및 "
            "관리자 보정점수가 반영됩니다.",
        )
        return redirect(f"{request.path}?round={selected_round.id}")

    return render(request, "admin_ui/evaluation_results.html", _base_context(**context))
