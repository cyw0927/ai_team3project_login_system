from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .common import _base_context, _default_destination, _social_login_context
from ..signup_forms import StudentSignupForm


LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_SECONDS = 300


def _client_ip(request):
    """로그인 제한에 사용할 클라이언트 IP를 안전한 신뢰 정책으로 결정한다."""
    remote_addr = request.META.get("REMOTE_ADDR", "unknown")
    if getattr(settings, "LOGIN_TRUST_X_FORWARDED_FOR", False):
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip() or remote_addr
    return remote_addr


def _login_rate_key(request, login_id):
    client_ip = _client_ip(request)
    normalized_login = (login_id or "").strip().lower()
    return f"login-failures:{client_ip}:{normalized_login}"


def _login_is_limited(request, login_id):
    return int(cache.get(_login_rate_key(request, login_id), 0) or 0) >= LOGIN_MAX_FAILURES


def _record_login_failure(request, login_id):
    key = _login_rate_key(request, login_id)
    try:
        failures = cache.incr(key)
    except ValueError:
        cache.set(key, 1, LOGIN_LOCK_SECONDS)
        failures = 1
    if failures == 1:
        cache.touch(key, LOGIN_LOCK_SECONDS)


def _clear_login_failures(request, login_id):
    cache.delete(_login_rate_key(request, login_id))


def login_page(request):
    if request.user.is_authenticated:
        return redirect(_default_destination(request.user))

    form_data = {"username": ""}

    if request.method == "POST":
        login_id = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        form_data["username"] = login_id

        if not login_id or not password:
            return render(
                request,
                "login.html",
                _base_context(
                    form_data=form_data,
                    error_message="아이디(또는 이메일)와 비밀번호를 입력해주세요.",
                    **_social_login_context(),
                ),
            )

        if _login_is_limited(request, login_id):
            return render(
                request,
                "login.html",
                _base_context(
                    form_data=form_data,
                    error_message="로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.",
                    **_social_login_context(),
                ),
                status=429,
            )

        # Django 기본 로그인은 username을 사용한다.
        # 이메일 로그인은 중복 이메일이 없는 경우에만 허용한다.
        auth_username = login_id
        if "@" in login_id:
            matches = list(User.objects.filter(email__iexact=login_id).only("username")[:2])
            if len(matches) > 1:
                _record_login_failure(request, login_id)
                return render(
                    request,
                    "login.html",
                    _base_context(
                        form_data=form_data,
                        error_message="동일 이메일 계정이 여러 개 존재합니다. 아이디로 로그인해주세요.",
                        **_social_login_context(),
                    ),
                )
            if matches:
                auth_username = matches[0].username

        user = authenticate(request, username=auth_username, password=password)

        if user is None:
            _record_login_failure(request, login_id)
            return render(
                request,
                "login.html",
                _base_context(
                    form_data=form_data,
                    error_message="아이디 또는 비밀번호가 올바르지 않습니다.",
                    **_social_login_context(),
                ),
            )

        if not user.is_active:
            _record_login_failure(request, login_id)
            return render(
                request,
                "login.html",
                _base_context(
                    form_data=form_data,
                    error_message="비활성화된 계정입니다. 관리자에게 문의해주세요.",
                    **_social_login_context(),
                ),
            )

        if not (user.is_staff or user.is_superuser):
            student = getattr(user, "student_profile", None)
            if not student or not student.is_active:
                _record_login_failure(request, login_id)
                return render(
                    request,
                    "login.html",
                    _base_context(
                        form_data=form_data,
                        error_message="등록된 활성 수강생 계정이 아닙니다.",
                        **_social_login_context(),
                    ),
                )

        _clear_login_failures(request, login_id)
        login(request, user)

        # 로그인 상태 유지 체크 시 14일간 세션을 유지하고, 미체크 시 브라우저 종료 때 만료한다.
        if request.POST.get("remember_me") == "1":
            request.session.set_expiry(60 * 60 * 24 * 14)
        else:
            request.session.set_expiry(0)

        next_url = request.POST.get("next") or request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)

        return redirect(_default_destination(user))

    return render(
        request,
        "login.html",
        _base_context(
            form_data=form_data,
            **_social_login_context(),
        ),
    )


def signup_page(request):
    """수강생이 직접 아이디/비밀번호를 만드는 일반 회원가입."""
    if request.user.is_authenticated:
        return redirect(_default_destination(request.user))

    form = StudentSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        # ModelBackend와 allauth backend를 함께 쓰므로 신규 User를 직접 login()할 때
        # 어떤 backend로 세션을 만들지 명시해야 한다.
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        request.session.set_expiry(0)
        messages.success(request, "회원가입이 완료되었습니다. 수강생 계정으로 로그인했습니다.")
        return redirect("student_home")

    return render(
        request,
        "signup.html",
        _base_context(
            signup_form=form,
            **_social_login_context(),
        ),
    )


@login_required
@require_POST
def logout_view(request):
    if request.method == "POST":
        logout(request)
        messages.success(request, "로그아웃되었습니다.")
        return redirect("login")

    return redirect(_default_destination(request.user))
