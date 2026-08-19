"""Django settings for AX evaluation system."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-change-this-key-before-production",
)
DEBUG = os.getenv("DJANGO_DEBUG", "1").lower() in {"1", "true", "yes", "on"}
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]

# 개발용 Cloudflare Quick Tunnel 허용.
# .trycloudflare.com은 하위 도메인을 모두 허용하므로 터널 주소가 바뀌어도
# settings.py를 다시 수정할 필요가 없습니다.
if ".trycloudflare.com" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(".trycloudflare.com")

# Cloudflare가 외부 HTTPS 요청을 로컬 Django HTTP 서버로 전달할 때
# Django가 원래 요청을 HTTPS로 인식하도록 합니다.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Cloudflare Quick Tunnel에서 들어오는 POST 요청(로그인/로그아웃 등)의
# CSRF 검증을 허용합니다. Django 4+는 와일드카드 origin을 지원합니다.
CSRF_TRUSTED_ORIGINS = [
    "https://*.trycloudflare.com",
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.kakao",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "dashboard.middleware.AdminActivityLogMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "dashboard.context_processors.notification_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database -------------------------------------------------------------------
# 교육과정 기준 PostgreSQL 사용. 실제 접속 정보는 .env에서 읽습니다.
# 기본 스키마는 practice이며, ORM이 practice -> public 순서로 검색합니다.
DB_NAME = os.getenv("DB_NAME", "postgres").strip() or "postgres"
DB_USER = os.getenv("DB_USER", "postgres").strip() or "postgres"
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1").strip() or "127.0.0.1"
DB_PORT = os.getenv("DB_PORT", "5432").strip() or "5432"
DB_SCHEMA = os.getenv("DB_SCHEMA", "practice").strip() or "practice"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": DB_NAME,
        "USER": DB_USER,
        "PASSWORD": DB_PASSWORD,
        "HOST": DB_HOST,
        "PORT": DB_PORT,
        "OPTIONS": {
            "options": f"-c search_path={DB_SCHEMA},public",
        },
        "CONN_MAX_AGE": 60,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "student_home"
LOGOUT_REDIRECT_URL = "login"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Social OAuth ---------------------------------------------------------------
# 이 프로젝트는 OAuth 자격증명을 Django admin SocialApp이 아니라 .env -> settings.py 방식으로 관리합니다.
# 같은 provider를 SocialApp에도 중복 등록하면 allauth가 어떤 앱을 써야 할지 결정하지 못할 수 있으므로
# Google/Kakao SocialApp 레코드는 별도로 만들지 않는 것을 원칙으로 합니다.
# 외부 OAuth 콘솔에서 발급받은 값을 .env에 넣으면 실제 소셜 로그인이 동작합니다.
GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()

# Kakao의 client_id에는 "REST API 키", secret에는 "Client secret"을 넣습니다.
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "").strip()
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", "").strip()

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "OAUTH_PKCE_ENABLED": True,
        "EMAIL_AUTHENTICATION": True,
        "EMAIL_AUTHENTICATION_AUTO_CONNECT": True,
    },
    # 카카오는 UID 기반 인증만 사용합니다. 별도 개인정보 scope를 요청하지 않습니다.
    "kakao": {},
}

if GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET:
    SOCIALACCOUNT_PROVIDERS["google"]["APPS"] = [
        {
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "secret": GOOGLE_OAUTH_CLIENT_SECRET,
            "key": "",
        }
    ]

if KAKAO_REST_API_KEY and KAKAO_CLIENT_SECRET:
    SOCIALACCOUNT_PROVIDERS["kakao"]["APPS"] = [
        {
            "client_id": KAKAO_REST_API_KEY,
            "secret": KAKAO_CLIENT_SECRET,
            "key": "",
        }
    ]

SOCIALACCOUNT_ADAPTER = "dashboard.adapters.ExistingUserOnlySocialAccountAdapter"
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
# 소셜 로그인 시작은 POST 요청으로 수행합니다. login.html의 provider_login_url form과 짝을 이룹니다.
SOCIALACCOUNT_LOGIN_ON_GET = False
