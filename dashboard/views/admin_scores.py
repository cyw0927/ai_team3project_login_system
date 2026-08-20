from django.contrib import messages
from django.shortcuts import redirect, render

from .common import _base_context, _current_round, admin_required
from ..models import EvaluationRound
from ..services.result_service import recalculate_round_results
from ..services.score_read_service import (
    build_personal_score_rows,
    build_ranking_rows,
    build_team_score_rows,
)


def _selected_round(request):
    rounds = EvaluationRound.objects.all().order_by("-start_at")
    round_id = request.GET.get("round") or request.POST.get("round_id")
    selected_round = rounds.filter(pk=round_id).first() if round_id else _current_round()
    return rounds, selected_round


@admin_required
def admin_team_scores(request):
    rounds, selected_round = _selected_round(request)
    if request.method == "POST" and selected_round:
        recalculate_round_results(selected_round)
        messages.success(request, "팀 점수를 다시 계산했습니다.")
        return redirect(f"{request.path}?round={selected_round.id}")

    return render(
        request,
        "admin_ui/team_scores.html",
        _base_context(
            rounds=rounds,
            selected_round=selected_round,
            team_scores=build_team_score_rows(selected_round),
        ),
    )


@admin_required
def admin_personal_scores(request):
    rounds, selected_round = _selected_round(request)
    if request.method == "POST" and selected_round:
        recalculate_round_results(selected_round)
        messages.success(request, "개인 점수를 다시 계산했습니다.")
        return redirect(f"{request.path}?round={selected_round.id}")

    return render(
        request,
        "admin_ui/personal_scores.html",
        _base_context(
            rounds=rounds,
            selected_round=selected_round,
            personal_scores=build_personal_score_rows(selected_round),
        ),
    )


@admin_required
def admin_rankings(request):
    rounds, selected_round = _selected_round(request)
    if request.method == "POST" and selected_round:
        recalculate_round_results(selected_round)
        messages.success(request, "순위를 다시 계산했습니다.")
        return redirect(f"{request.path}?round={selected_round.id}")

    return render(
        request,
        "admin_ui/rankings.html",
        _base_context(
            rounds=rounds,
            selected_round=selected_round,
            rankings=build_ranking_rows(selected_round),
        ),
    )
