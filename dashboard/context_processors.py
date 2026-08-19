from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone

from .models import Announcement, AnnouncementRead, InternalMessage, EvaluationRound, ResultPublishSetting, StudentBadge, AdminStudentComment


def notification_context(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"notification_badge_count": 0}

    now = timezone.now()
    active = Announcement.objects.filter(
        is_published=True,
        target_all=True,
        publish_at__lte=now,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))

    if request.user.is_staff or request.user.is_superuser:
        return {"notification_badge_count": active.count()}

    student = getattr(request.user, "student_profile", None)
    if not student:
        return {"notification_badge_count": 0}

    read_ids = AnnouncementRead.objects.filter(student=student).values_list("announcement_id", flat=True)
    unread = active.exclude(id__in=read_ids)
    popup = (
        unread.annotate(
            popup_priority=Case(
                When(priority=Announcement.Priority.URGENT, then=Value(3)),
                When(priority=Announcement.Priority.IMPORTANT, then=Value(2)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .order_by("-popup_priority", "-publish_at", "-id")
        .first()
    )
    current_round = (
        EvaluationRound.objects.filter(is_current=True).order_by("-updated_at").first()
        or EvaluationRound.objects.filter(status=EvaluationRound.Status.IN_PROGRESS).order_by("-start_at").first()
    )
    visible_badges = []
    if current_round:
        publish_setting = ResultPublishSetting.objects.filter(evaluation_round=current_round).first()
        is_result_visible = bool(
            publish_setting
            and (publish_setting.is_published or (publish_setting.publish_at and publish_setting.publish_at <= now))
        )
        if is_result_visible:
            visible_badges = list(
                StudentBadge.objects.filter(student=student, evaluation_round=current_round)
                .order_by("badge_type")
            )

    return {
        "notification_badge_count": unread.count(),
        "message_badge_count": InternalMessage.objects.filter(recipient=student, read_at__isnull=True, recalled_at__isnull=True).count(),
        "feedback_badge_count": AdminStudentComment.objects.filter(student=student, read_at__isnull=True).count(),
        # 학생 화면에 진입했을 때 아직 확인하지 않은 전체 공지를 크게 노출한다.
        "popup_announcement": popup,
        "student_badges": visible_badges,
        "student_has_mvp_badge": any(b.badge_type == StudentBadge.BadgeType.MVP for b in visible_badges),
    }
