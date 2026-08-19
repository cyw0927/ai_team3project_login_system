# Google / Kakao OAuth 설정 요약

## Google

`.env`

```env
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
```

Redirect URI:

```text
http://127.0.0.1:8000/accounts/google/login/callback/
http://localhost:8000/accounts/google/login/callback/
```

Authorized origin:

```text
http://127.0.0.1:8000
http://localhost:8000
```

## Kakao

`.env`

```env
KAKAO_REST_API_KEY=
KAKAO_CLIENT_SECRET=
```

Redirect URI:

```text
http://127.0.0.1:8000/accounts/kakao/login/callback/
http://localhost:8000/accounts/kakao/login/callback/
```

Kakao Login 사용 설정을 ON으로 켭니다.

## 확인

```cmd
python manage.py check_login_setup
```

프로젝트는 `.env -> settings.py` 방식으로 Social App을 등록하므로
Django Admin의 SocialApp에는 Google/Kakao를 중복 등록하지 않는 것이 원칙입니다.
