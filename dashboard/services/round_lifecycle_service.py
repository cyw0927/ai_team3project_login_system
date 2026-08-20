"""Evaluation-round lifecycle operations.

Views handle HTTP concerns; this service owns round state transitions and destructive
round cleanup rules.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ..models import (
    Assignment,
    EvaluationRound,
    EvaluationTemplate,
    PersonalEvaluationScore,
    Team,
    TeamEvaluationScore,
)


@transaction.atomic
def delete_round(evaluation_round):
    """Delete a round and return the replacement current round, if any."""
    was_current = evaluation_round.is_current
    round_id = evaluation_round.id

    # Evaluation score criterion FKs are protected, so score rows must go first.
    TeamEvaluationScore.objects.filter(
        evaluation__evaluation_round=evaluation_round
    ).delete()
    PersonalEvaluationScore.objects.filter(
        evaluation__evaluation_round=evaluation_round
    ).delete()

    deleted_count, _ = EvaluationRound.objects.filter(pk=round_id).delete()
    if deleted_count <= 0 or EvaluationRound.objects.filter(pk=round_id).exists():
        return False, None

    replacement = None
    if was_current:
        replacement = (
            EvaluationRound.objects.filter(status=EvaluationRound.Status.IN_PROGRESS)
            .order_by("-start_at")
            .first()
            or EvaluationRound.objects.order_by("-start_at").first()
        )
        if replacement:
            EvaluationRound.objects.filter(pk=replacement.pk).update(is_current=True)

    return True, replacement


def evaluation_start_missing_items(evaluation_round):
    """Return human-readable prerequisites still missing before evaluation start."""
    missing = []
    if not Assignment.objects.filter(evaluation_round=evaluation_round).exists():
        missing.append("과제")
    if not Team.objects.filter(evaluation_round=evaluation_round, is_active=True).exists():
        missing.append("팀 편성")
    if not evaluation_round.evaluation_templates.filter(
        is_active=True,
        evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
    ).exists():
        missing.append("팀 평가 템플릿")
    if not evaluation_round.evaluation_templates.filter(
        is_active=True,
        evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
    ).exists():
        missing.append("개인 평가 템플릿")
    return missing


@transaction.atomic
def apply_round_action(evaluation_round, action):
    """Apply one lifecycle action and return (level, message).

    level is one of success/info/error and is intentionally presentation-neutral
    enough for the view to map onto Django messages.
    """
    now = timezone.now()

    if action == "set_current":
        EvaluationRound.objects.filter(is_current=True).exclude(
            pk=evaluation_round.pk
        ).update(is_current=False)
        if not evaluation_round.is_current:
            evaluation_round.is_current = True
            evaluation_round.save(update_fields=["is_current", "updated_at"])
        return "success", f"{evaluation_round.name}을(를) 현재 회차로 지정했습니다."

    if action in {"start", "round_start"}:
        if evaluation_round.status != EvaluationRound.Status.SCHEDULED:
            return "error", "예정 상태의 회차만 시작할 수 있습니다."
        evaluation_round.status = EvaluationRound.Status.IN_PROGRESS
        evaluation_round.evaluation_started = False
        evaluation_round.is_locked = False
        if evaluation_round.start_at > now:
            evaluation_round.start_at = now
        evaluation_round.save()
        return "success", (
            f"{evaluation_round.name} 회차를 시작했습니다. "
            "평가 시작 전까지 과제 등록·수정과 학생 제출이 가능합니다."
        )

    if action in {"evaluation_start", "eval_start"}:
        if (
            evaluation_round.status != EvaluationRound.Status.IN_PROGRESS
            or evaluation_round.evaluation_started
        ):
            return "error", "진행 중이며 아직 평가를 시작하지 않은 회차에서만 평가를 시작할 수 있습니다."
        missing = evaluation_start_missing_items(evaluation_round)
        if missing:
            return "error", "평가 시작 전 준비가 필요합니다: " + ", ".join(missing)
        evaluation_round.evaluation_started = True
        evaluation_round.is_reopened = True
        evaluation_round.is_locked = False
        evaluation_round.save()
        return "success", (
            f"{evaluation_round.name} 평가를 시작했습니다. "
            "과제 등록·수정·제출은 이제 마감되고 평가 입력이 열립니다."
        )

    if action in {"lock", "pause"}:
        if (
            evaluation_round.status != EvaluationRound.Status.IN_PROGRESS
            or not evaluation_round.evaluation_started
        ):
            return "error", "평가가 시작된 진행 중 회차만 일시 중단할 수 있습니다."
        if evaluation_round.is_locked:
            return "info", f"{evaluation_round.name} 평가는 이미 중단된 상태입니다."
        evaluation_round.is_locked = True
        evaluation_round.save(update_fields=["is_locked", "updated_at"])
        return "success", (
            f"{evaluation_round.name} 평가를 일시 중단했습니다. "
            "기존 임시저장·제출 데이터는 그대로 유지됩니다."
        )

    if action in {"unlock", "resume"}:
        if (
            evaluation_round.status != EvaluationRound.Status.IN_PROGRESS
            or not evaluation_round.evaluation_started
        ):
            return "error", "평가가 시작된 진행 중 회차만 재개할 수 있습니다."
        if not evaluation_round.is_locked:
            return "info", f"{evaluation_round.name} 평가는 이미 진행 중입니다."
        evaluation_round.is_locked = False
        evaluation_round.save(update_fields=["is_locked", "updated_at"])
        return "success", (
            f"{evaluation_round.name} 평가를 재개했습니다. "
            "학생들이 다시 임시저장·제출할 수 있습니다."
        )

    if action == "end":
        if (
            evaluation_round.status != EvaluationRound.Status.IN_PROGRESS
            or not evaluation_round.evaluation_started
        ):
            return "error", "평가가 시작된 진행 중 회차만 종료할 수 있습니다."
        evaluation_round.status = EvaluationRound.Status.ENDED
        evaluation_round.evaluation_started = False
        evaluation_round.is_reopened = False
        evaluation_round.is_locked = True
        if evaluation_round.end_at > now:
            evaluation_round.end_at = now
        evaluation_round.save()
        return "success", f"{evaluation_round.name} 평가를 종료했습니다."

    if action == "reopen":
        if evaluation_round.status != EvaluationRound.Status.ENDED:
            return "error", "종료된 회차만 다시 열 수 있습니다."
        evaluation_round.status = EvaluationRound.Status.IN_PROGRESS
        evaluation_round.evaluation_started = True
        evaluation_round.is_reopened = True
        evaluation_round.is_locked = False
        if evaluation_round.end_at <= now:
            evaluation_round.end_at = now + timedelta(days=1)
        evaluation_round.save()
        return "success", f"{evaluation_round.name} 평가를 다시 열었습니다."

    return "error", "지원하지 않는 회차 작업입니다."
