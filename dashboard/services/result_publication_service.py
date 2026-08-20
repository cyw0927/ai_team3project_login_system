"""Result publication policy and persistence."""

from datetime import datetime

from django.utils import timezone

from ..models import ResultPublishSetting
from .result_service import recalculate_round_results


PUBLISH_OPTION_FIELDS = (
    ("show_team_first_place", "팀 1위 공개"),
    ("show_all_team_ranks", "전체 팀 순위 공개"),
    ("show_personal_score", "개인 점수 공개"),
    ("show_overall_rank", "개인 종합 순위 공개"),
    ("show_comments", "평가 코멘트 공개"),
)


def get_or_create_publish_setting(evaluation_round):
    if not evaluation_round:
        return None
    setting, _ = ResultPublishSetting.objects.get_or_create(
        evaluation_round=evaluation_round
    )
    return setting


def parse_publish_at(raw_value):
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return None
    try:
        value = datetime.fromisoformat(raw_value)
    except ValueError:
        return None
    return timezone.make_aware(value) if timezone.is_naive(value) else value


def update_publish_setting(setting, post_data):
    """Apply one admin publication action and return a user-facing message."""
    for field, _label in PUBLISH_OPTION_FIELDS:
        setattr(setting, field, field in post_data)

    setting.publish_at = parse_publish_at(post_data.get("publish_at"))
    action = post_data.get("action", "save")

    if action == "publish":
        recalculate_round_results(setting.evaluation_round)
        setting.is_published = True
        setting.publish_at = timezone.now()
        message = "결과를 즉시 공개했습니다."
    elif action == "unpublish":
        setting.is_published = False
        setting.publish_at = None
        message = "결과 공개를 중지했습니다."
    else:
        if setting.publish_at and setting.publish_at > timezone.now():
            setting.is_published = False
        message = "결과 공개 설정을 저장했습니다."

    setting.save()
    return message


def publish_options(setting):
    if not setting:
        return []
    return [
        {"key": field, "label": label, "enabled": getattr(setting, field)}
        for field, label in PUBLISH_OPTION_FIELDS
    ]


def effective_published(setting, now=None):
    if not setting:
        return False
    now = now or timezone.now()
    return bool(
        setting.is_published
        or (setting.publish_at and setting.publish_at <= now)
    )
