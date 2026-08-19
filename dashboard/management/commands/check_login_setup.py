from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from allauth.socialaccount.models import SocialApp

from dashboard.models import Student


class Command(BaseCommand):
    help = "로그인 계정/OAuth 설정 상태를 비밀값 노출 없이 점검합니다."

    def _status(self, ok):
        return self.style.SUCCESS("OK") if ok else self.style.WARNING("NOT CONFIGURED")

    def handle(self, *args, **options):
        User = get_user_model()

        google_ready = bool(
            settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET
        )
        kakao_ready = bool(
            settings.KAKAO_REST_API_KEY and settings.KAKAO_CLIENT_SECRET
        )

        self.stdout.write("=== AX 로그인 / OAuth 설정 점검 ===")
        self.stdout.write(f"Google OAuth: {self._status(google_ready)}")
        self.stdout.write(f"Kakao OAuth : {self._status(kakao_ready)}")
        self.stdout.write(
            "SOCIALACCOUNT_LOGIN_ON_GET: "
            + str(getattr(settings, "SOCIALACCOUNT_LOGIN_ON_GET", None))
        )
        self.stdout.write("")

        # 이 프로젝트는 settings.py APPS 방식만 사용한다.
        google_db_apps = SocialApp.objects.filter(provider="google").count()
        kakao_db_apps = SocialApp.objects.filter(provider="kakao").count()

        self.stdout.write(
            f"DB SocialApp Google: {google_db_apps}개"
            + ("  [삭제 권장: .env/settings.py와 중복]" if google_db_apps else "")
        )
        self.stdout.write(
            f"DB SocialApp Kakao : {kakao_db_apps}개"
            + ("  [삭제 권장: .env/settings.py와 중복]" if kakao_db_apps else "")
        )
        self.stdout.write("")

        admin = User.objects.filter(username="admin01").first()
        student = User.objects.filter(username="student01").first()

        if admin:
            self.stdout.write(
                f"admin01: EXISTS / active={admin.is_active} / staff={admin.is_staff}"
            )
        else:
            self.stdout.write("admin01: NOT FOUND")

        if student:
            profile = Student.objects.filter(user=student).first()
            self.stdout.write(
                "student01: EXISTS / active={} / student_profile={}".format(
                    student.is_active,
                    "OK" if profile and profile.is_active else "MISSING/INACTIVE",
                )
            )
        else:
            self.stdout.write("student01: NOT FOUND")

        self.stdout.write("")
        self.stdout.write("로컬 Redirect URI")
        self.stdout.write(
            "Google: http://127.0.0.1:8000/accounts/google/login/callback/"
        )
        self.stdout.write(
            "Kakao : http://127.0.0.1:8000/accounts/kakao/login/callback/"
        )
        self.stdout.write("")
        self.stdout.write("※ 비밀번호, Client Secret 등 실제 비밀값은 출력하지 않습니다.")
