"""Single source of truth for evaluation score weights."""

DEFAULT_TEAM_WEIGHT = 40
DEFAULT_PERSONAL_WEIGHT = 30
DEFAULT_TUTOR_WEIGHT = 30


def tutor_weight_for(evaluation_round):
    """Return the tutor share stored implicitly as the remainder to 100."""
    team = int(evaluation_round.team_weight or 0)
    personal = int(evaluation_round.personal_weight or 0)
    return max(0, 100 - team - personal)


def validate_score_weights(team_weight, personal_weight, tutor_weight):
    """Validate a 3-part scoring policy and return normalized integers."""
    try:
        values = tuple(int(value) for value in (team_weight, personal_weight, tutor_weight))
    except (TypeError, ValueError):
        return None, "가중치는 숫자로 입력해 주세요."

    if any(value < 0 or value > 100 for value in values):
        return None, "가중치는 0~100 사이여야 합니다."
    if sum(values) != 100:
        return None, "팀·개인·튜터 평가 가중치 합계는 100%여야 합니다."

    return {
        "team_weight": values[0],
        "personal_weight": values[1],
        "tutor_weight": values[2],
    }, None
