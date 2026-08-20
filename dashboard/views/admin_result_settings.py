from django.contrib import messages
from django.shortcuts import redirect, render

from .common import _base_context, admin_required
from ..models import EvaluationRound
from ..services.result_publication_service import (
    effective_published,
    get_or_create_publish_setting,
    publish_options,
    update_publish_setting,
)


def _selected_round(request, rounds):
    round_id = request.POST.get("round_id") or request.GET.get("round")
    if round_id:
        selected = rounds.filter(pk=round_id).first()
        if selected:
            return selected
    return rounds.filter(is_current=True).first() or rounds.first()


@admin_required
def admin_result_settings(request):
    rounds = EvaluationRound.objects.all().order_by("-start_at")
    selected_round = _selected_round(request, rounds)
    setting = get_or_create_publish_setting(selected_round)

    if request.method == "POST" and selected_round and setting:
        message = update_publish_setting(setting, request.POST)
        messages.success(request, message)
        return redirect(f"{request.path}?round={selected_round.id}")

    return render(
        request,
        "admin_ui/result_settings.html",
        _base_context(
            rounds=rounds,
            selected_round=selected_round,
            setting=setting,
            publish_options=publish_options(setting),
            effective_published=effective_published(setting),
        ),
    )
