# Git 반영 가이드

## 1. 새 브랜치 생성
```powershell
git switch -c feature/v2-redesign
```

## 2. 최종 파일 복사 후 상태 확인
```powershell
git status
```

`.env`, `.venv`, `media`, `__pycache__`가 staged 대상에 보이면 안 됩니다.

## 3. 사전 검사
```powershell
python tools\pre_release_check.py
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test dashboard
```

DB가 연결되어 있다면:
```powershell
python manage.py migrate
```

## 4. 커밋
```powershell
git add -A
git diff --cached --check
git status
git commit -m "feat: improve AX evaluation workflow and UI"
```

## 5. 푸시
```powershell
git push -u origin feature/v2-redesign
```

GitHub에서 Pull Request를 만든 뒤 main에 병합합니다.
