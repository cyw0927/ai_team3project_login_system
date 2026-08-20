from .common import *
from ..signup_forms import StudentSignupForm


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

        # Django 기본 로그인은 username을 사용한다.
        # 이메일이 입력되면 해당 이메일의 username을 찾아 인증한다.
        auth_username = login_id
        if "@" in login_id:
            from django.contrib.auth.models import User

            matched_user = User.objects.filter(email__iexact=login_id).first()
            if matched_user:
                auth_username = matched_user.username

        user = authenticate(request, username=auth_username, password=password)

        if user is None:
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
                return render(
                    request,
                    "login.html",
                    _base_context(
                        form_data=form_data,
                        error_message="등록된 활성 수강생 계정이 아닙니다.",
                        **_social_login_context(),
                    ),
                )

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
