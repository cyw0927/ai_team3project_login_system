from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .common import _redirect_back, admin_required
from ..forms import EvaluationRoundForm
from ..models import EvaluationRound
from ..services.round_lifecycle_service import apply_round_action, delete_round


def _message(request, level, text):
    getattr(messages, level)(request, text)


@admin_required
@require_POST
@transaction.atomic
def admin_round_update(request, round_id):
    evaluation_round = get_object_or_404(EvaluationRound, pk=round_id)
    if evaluation_round.status != EvaluationRound.Status.SCHEDULED:
        messages.error(request, "시작된 평가 회차는 기간과 회차명을 수정할 수 없습니다.")
        return _redirect_back(request, "admin_rounds")

    form = EvaluationRoundForm(request.POST, instance=evaluation_round)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return _redirect_back(request, "admin_rounds")

    evaluation_round = form.save(commit=False)
    evaluation_round.status = EvaluationRound.Status.SCHEDULED
    evaluation_round.evaluation_started = False
    evaluation_round.save()
    messages.success(request, f"{evaluation_round.name} 회차를 수정했습니다.")
    return _redirect_back(request, "admin_rounds")


@admin_required
@require_POST
@transaction.atomic
def admin_round_delete(request, round_id):
    evaluation_round = get_object_or_404(EvaluationRound, pk=round_id)
    name = evaluation_round.name
    deleted, _replacement = delete_round(evaluation_round)
    if not deleted:
        messages.error(request, f"{name} 회차 삭제에 실패했습니다. 다시 시도해주세요.")
        return _redirect_back(request, "admin_rounds")

    messages.success(request, f"{name} 회차와 연결 데이터를 삭제했습니다.")
    return _redirect_back(request, "admin_rounds")


@admin_required
@require_POST
def admin_round_action(request, round_id, action):
    evaluation_round = get_object_or_404(EvaluationRound, pk=round_id)
    level, text = apply_round_action(evaluation_round, action)
    _message(request, level, text)
    return _redirect_back(request, "admin_rounds")
