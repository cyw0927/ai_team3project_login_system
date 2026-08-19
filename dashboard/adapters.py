import re

from allauth.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import redirect

from .models import Student


class ExistingUserOnlySocialAccountAdapter(DefaultSocialAccountAdapter):
    """AX 소셜 로그인 규칙.

    Google / Kakao 공통
    ---------------------
    - 소셜 로그인은 학생 전용이다.
    - 최초 로그인 사용자는 일반 User + Student 프로필로 자동 생성한다.
    - 생성되는 계정은 is_staff=False / is_superuser=False 로 고정한다.
    - 기존 일반 사용자와 이메일이 일치하면 해당 계정에 연결하고 Student 프로필을 보장한다.
    - 기존 관리자(is_staff/is_superuser) 이메일과 일치하면 소셜 로그인을 차단한다.
    - 이미 연결된 소셜 계정이라도 관리자 계정이면 소셜 로그인을 차단한다.
    """

    STUDENT_ONLY_PROVIDERS = {"google", "kakao"}

    def _provider_label(self, provider):
        return {"google": "Google", "kakao": "카카오"}.get(provider, "소셜")

    def _verified_email(self, sociallogin):
        # allauth가 표준화한 verified email을 먼저 사용한다.
        verified_emails = [
            (address.email or "").strip()
            for address in getattr(sociallogin, "email_addresses", [])
            if getattr(address, "verified", False) and getattr(address, "email", None)
        ]
        if verified_emails:
            return verified_emails[0]

        # Kakao는 provider 응답 형태에 따라 email_addresses에 verified 플래그가
        # 안 잡히는 경우가 있어 extra_data도 보조적으로 확인한다.
        provider = getattr(sociallogin.account, "provider", "")
        extra = getattr(sociallogin.account, "extra_data", {}) or {}
        if provider == "kakao":
            account = extra.get("kakao_account") or {}
            email = (account.get("email") or "").strip()
            # 이메일이 내려왔고 Kakao 계정 이메일 유효성 플래그가 명시적으로 false가 아니면 사용한다.
            if email and account.get("is_email_valid", True) and account.get("is_email_verified", True):
                return email

        return ""

    def _unique_username(self, provider, sociallogin, email=""):
        User = get_user_model()
        uid = str(getattr(sociallogin.account, "uid", "") or "")
        seed = uid or (email.split("@", 1)[0] if email else "user")
        seed = re.sub(r"[^A-Za-z0-9_.-]", "", seed)[:120] or "user"
        base = f"{provider}_{seed}"[:150]
        username = base
        suffix = 1
        while User.objects.filter(username=username).exists():
            tail = f"_{suffix}"
            username = f"{base[:150-len(tail)]}{tail}"
            suffix += 1
        return username

    def _profile_names(self, provider, sociallogin):
        extra = getattr(sociallogin.account, "extra_data", {}) or {}

        if provider == "google":
            first_name = (extra.get("given_name") or "").strip()
            last_name = (extra.get("family_name") or "").strip()
            if not first_name and not last_name:
                first_name = (extra.get("name") or "").strip()[:150]
            return first_name[:150], last_name[:150]

        if provider == "kakao":
            account = extra.get("kakao_account") or {}
            profile = account.get("profile") or {}
            nickname = (profile.get("nickname") or "").strip()
            if not nickname:
                properties = extra.get("properties") or {}
                nickname = (properties.get("nickname") or "").strip()
            return nickname[:150], ""

        return "", ""

    def _deny_admin_social_login(self, request, provider):
        label = self._provider_label(provider)
        messages.error(
            request,
            f"관리자 계정은 {label} 로그인을 사용할 수 없습니다. 관리자 아이디와 비밀번호로 로그인해주세요.",
        )
        raise ImmediateHttpResponse(redirect("login"))

    @transaction.atomic
    def _handle_student_only_provider(self, request, sociallogin, provider):
        User = get_user_model()
        label = self._provider_label(provider)

        # 이미 연결된 소셜 계정도 관리자라면 소셜 경로로 관리자 화면에 들어갈 수 없게 차단한다.
        if sociallogin.is_existing:
            user = sociallogin.user
            if user.is_staff or user.is_superuser:
                self._deny_admin_social_login(request, provider)

            if not user.is_active:
                messages.error(request, "비활성화된 계정입니다. 관리자에게 문의해주세요.")
                raise ImmediateHttpResponse(redirect("login"))

            Student.objects.get_or_create(user=user, defaults={"is_active": True})
            return

        email = self._verified_email(sociallogin)

        # 이메일이 있으면 기존 AX 계정과 안전하게 연결한다.
        if email:
            matched_user = User.objects.filter(email__iexact=email).first()
            if matched_user:
                if matched_user.is_staff or matched_user.is_superuser:
                    self._deny_admin_social_login(request, provider)

                if not matched_user.is_active:
                    messages.error(request, "비활성화된 계정입니다. 관리자에게 문의해주세요.")
                    raise ImmediateHttpResponse(redirect("login"))

                # 혹시 과거에 일반 User만 있던 경우 학생 프로필을 자동 생성한다.
                Student.objects.get_or_create(user=matched_user, defaults={"is_active": True})
                sociallogin.connect(request, matched_user)
                return

        # 최초 Google/Kakao 로그인은 무조건 학생 계정으로 생성한다.
        # Kakao에서 이메일 제공 동의를 하지 않아 이메일이 없는 경우에도 Kakao UID 기반으로 학생 계정 생성 가능.
        first_name, last_name = self._profile_names(provider, sociallogin)
        new_user = User.objects.create_user(
            username=self._unique_username(provider, sociallogin, email),
            email=email,
            first_name=first_name,
            last_name=last_name,
        )
        new_user.set_unusable_password()
        new_user.is_active = True
        new_user.is_staff = False
        new_user.is_superuser = False
        new_user.save(update_fields=["password", "is_active", "is_staff", "is_superuser"])

        Student.objects.create(user=new_user, is_active=True)
        sociallogin.connect(request, new_user)

        if provider == "kakao" and not email:
            messages.info(
                request,
                "카카오 이메일 제공 없이 학생 계정이 생성되었습니다. 필요하면 관리자에게 이메일 등록을 요청해주세요.",
            )

    def pre_social_login(self, request, sociallogin):
        provider = getattr(sociallogin.account, "provider", "")
        if provider in self.STUDENT_ONLY_PROVIDERS:
            self._handle_student_only_provider(request, sociallogin, provider)
            return

        # 현재 AX 시스템에서 별도로 허용하지 않은 다른 provider는 신규 가입을 열지 않는다.
        if not sociallogin.is_existing:
            messages.error(request, "허용되지 않은 소셜 로그인 방식입니다.")
            raise ImmediateHttpResponse(redirect("login"))

    def is_open_for_signup(self, request, sociallogin):
        # Google/Kakao 신규 사용자는 pre_social_login에서 Student까지 직접 생성한다.
        # allauth의 일반 회원가입 화면은 사용하지 않는다.
        return False
