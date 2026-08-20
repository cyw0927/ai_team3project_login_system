"""Administrator score-adjustment validation and persistence."""

from decimal import Decimal, InvalidOperation

from .result_service import recalculate_round_results


def parse_adjustment(raw_score, reason):
    try:
        adjustment = Decimal((raw_score or "0").strip())
    except InvalidOperation:
        return None, None, "보정점수는 숫자로 입력해 주세요."

    reason = (reason or "").strip()
    if adjustment != 0 and not reason:
        return None, None, "보정점수를 적용할 때는 사유를 입력해 주세요."
    return adjustment, reason, None


def save_adjustment(result, adjustment, reason):
    result.adjustment_score = adjustment
    result.adjustment_reason = reason if adjustment != 0 else ""
    result.save(
        update_fields=[
            "adjustment_score",
            "adjustment_reason",
            "updated_at",
        ]
    )
    recalculate_round_results(result.evaluation_round)
    return result
