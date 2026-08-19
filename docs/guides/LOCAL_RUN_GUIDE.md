# 로컬 실행 가이드

## 일반 실행
CMD에서 프로젝트 폴더로 이동 후:

```cmd
tools\run_local.bat
```

이 스크립트는:
1. `.venv` 확인
2. `.env`가 없으면 `.env.example` 복사
3. `python manage.py check`
4. `python manage.py migrate`
5. `python manage.py runserver`

순서로 실행합니다.

## 데모 실행
데모 데이터가 필요한 경우:

```cmd
tools\run_demo.bat
```

주의: `seed_demo`는 데모/테스트 DB에서만 사용하세요.

## 접속
`http://127.0.0.1:8000/`
