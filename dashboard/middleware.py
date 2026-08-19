from django.db import OperationalError, ProgrammingError

from .models import AdminActivityLog


SENSITIVE_KEYS = {
    "csrfmiddlewaretoken", "password", "password1", "password2",
    "current_password", "new_password", "new_password1", "new_password2",
    "client_secret", "secret", "token",
}


def _safe_payload(post):
    payload = {}
    for key in post.keys():
        lowered = key.lower()
        if lowered in SENSITIVE_KEYS or "password" in lowered or "secret" in lowered or "token" in lowered:
            payload[key] = "[REDACTED]"
            continue
        values = post.getlist(key)
        cleaned = [str(value)[:180] for value in values[:20]]
        payload[key] = cleaned if len(cleaned) > 1 else (cleaned[0] if cleaned else "")
    return payload


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.META.get("REMOTE_ADDR", "")[:64]


def _action_info(path, post):
    action = str(post.get("action", "")).strip().lower()

    rules = [
        ("/data/restore/", "data_restore", "운영 데이터 복원"),
        ("/students/excel-upload/", "student_excel_upload", "수강생 Excel 업로드"),
        ("/students/create/", "student_create", "수강생 등록"),
        ("/reset-password/", "student_password_reset", "수강생 비밀번호 초기화"),
        ("/toggle-active/", "student_toggle_active", "수강생 계정 상태 변경"),
        ("/students/", "student_update", "수강생 정보 변경"),
        ("/rounds/", "round_change", "평가회차 변경"),
        ("/assignments/", "assignment_change", "과제 변경"),
        ("/team-assignment/dissolve/", "team_dissolve", "전체 팀 해체"),
        ("/team-assignment/manual/assign/", "team_manual_assign", "수동 팀 배정"),
        ("/team-assignment/manual/unassign/", "team_manual_unassign", "팀 배정 해제"),
        ("/team-assignment/auto/confirm/", "team_auto_confirm", "자동 팀 편성 적용"),
        ("/team-assignment/auto/preview/", "team_auto_preview", "자동 팀 편성 미리보기"),
        ("/teams/create/", "team_create", "팀 생성"),
        ("/teams/", "team_change", "팀 정보 변경"),
        ("/evaluation-templates/", "template_change", "평가 템플릿 변경"),
        ("/evaluation-criteria/", "criterion_change", "평가 문항 변경"),
        ("/evaluation-results/weights/", "score_weight_change", "평가 가중치 변경"),
        ("/evaluation-results/", "result_change", "평가 결과 변경"),
        ("/result-settings/", "result_publish_change", "결과 공개 설정 변경"),
        ("/activity-logs/", "activity_log_cleanup", "활동 로그 정리"),
        ("/messages/", "message_management", "보낸 메시지 관리"),
        ("/announcements/", "announcement_change", "공지·알림 변경"),
    ]
    for fragment, key, label in rules:
        if fragment in path:
            if key == "announcement_change" and action:
                labels = {"create": "공지 등록", "update": "공지 수정", "delete": "공지 삭제", "toggle": "공지 공개 상태 변경"}
                return f"announcement_{action}", labels.get(action, label)
            return key, label
    return "admin_change", "관리자 변경 작업"


def _target_info(path, post):
    keys = [
        ("student", "student_id"), ("round", "round_id"), ("team", "team_id"),
        ("template", "template_id"), ("criterion", "criterion_id"),
        ("result", "result_id"), ("announcement", "announcement_id"),
        ("assignment", "assignment_id"),
    ]
    for target_type, key in keys:
        value = post.get(key)
        if value:
            return target_type, str(value)[:80]

    # URL 안의 숫자 PK를 보조적으로 기록한다.
    parts = [p for p in path.split("/") if p]
    for part in reversed(parts):
        if part.isdigit():
            return "object", part[:80]
    return "", ""


class AdminActivityLogMiddleware:
    """성공적으로 처리된 관리자 POST 요청을 자동 기록한다."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        user = getattr(request, "user", None)
        if not (
            request.method == "POST"
            and request.path.startswith("/management/")
            and user
            and user.is_authenticated
            and (user.is_staff or user.is_superuser)
            and response.status_code < 400
        ):
            return response

        try:
            action_key, action_label = _action_info(request.path, request.POST)
            target_type, target_id = _target_info(request.path, request.POST)
            payload = _safe_payload(request.POST)
            summary_bits = []
            for key in ("name", "title", "action", "round_id", "team_id", "student_id"):
                value = request.POST.get(key)
                if value:
                    summary_bits.append(f"{key}={str(value)[:60]}")
            AdminActivityLog.objects.create(
                actor=user,
                action_key=action_key,
                action_label=action_label,
                description=", ".join(summary_bits)[:300],
                path=request.path[:500],
                target_type=target_type,
                target_id=target_id,
                ip_address=_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
                metadata=payload,
            )
        except (OperationalError, ProgrammingError):
            # migrate 전에도 기존 관리자 기능 자체는 계속 동작해야 한다.
            pass
        except Exception:
            # 감사 로그 실패가 실제 업무 작업을 깨뜨리지 않게 한다.
            pass

        return response
