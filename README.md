# AX 수강생 평가 · 자동 팀 편성 시스템

Django + PostgreSQL 기반의 **수강생 평가, 결과 집계, 튜터 평가, Seed 기반 자동 팀 편성, 성장 관리** 통합 시스템입니다.

단순히 점수를 입력·조회하는 CRUD 프로젝트가 아니라, 실제 평가 운영 흐름을 하나의 서비스로 연결하는 것을 목표로 합니다.

## 프로젝트 핵심

- 학생 팀 평가 / 동료 개인 평가 / 튜터 팀 평가
- 권장 가중치 40:30:30
- 평가 결과를 누적 Seed로 변환해 다음 회차 팀 편성에 활용
- Z식 / FIFA 포트 / 균등 랜덤 3가지 자동 편성
- 실제 CSV 원본 보존 + canonical 데이터 분리
- View → Service → Model 구조로 리팩터링
- GitHub Actions로 Django check와 핵심 테스트 자동화

## 시연 화면

자동 편성 조건과 방식 선택 화면 및 세 알고리즘 비교 화면은 `docs/images/`에 보관합니다.

![자동 편성 조건과 포트 설정](docs/images/team_assignment_controls.jpg)

![Z식 FIFA 포트 완전랜덤 비교](docs/images/team_assignment_comparison.jpg)

## 자동 팀 편성

### Z식(Snake)
Seed 상위부터 팀을 왕복하며 배치합니다. 상위권 쏠림을 강하게 억제하고 Seed 보유자가 적어도 비교적 안정적인 균형을 만들 수 있어 현재 데이터에서는 우선 선택 방식으로 판단했습니다.

### FIFA 포트
A/B/C/D 포트로 나눈 뒤 포트별로 분산 배치합니다. 포트 누적 경계값을 조정할 수 있지만 Seed 수와 팀 수가 맞지 않으면 불균형이 생길 수 있어 경고를 표시합니다.

### 균등 랜덤
Seed를 사용하지 않고 활성 수강생을 무작위 배치합니다. 첫 회차처럼 Seed가 없을 때 적합하지만 실력 균형은 보장하지 않습니다.

## 데이터 이관 및 검증

```powershell
python manage.py rebuild_ax2_corrected .\data\ax2_personal.csv .\data\ax2_team.csv
python manage.py rebuild_ax2_corrected .\data\ax2_personal.csv .\data\ax2_team.csv --apply
python manage.py audit_ax2_consistency
```

## 설치 및 실행

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py prepare_postgres
python manage.py migrate
python manage.py check
python manage.py runserver
```

## 테스트와 CI

```powershell
python manage.py check
python manage.py test dashboard
```

GitHub Actions 워크플로가 push/PR 시 Django 기본 점검과 핵심 테스트를 자동 실행합니다.

## 향후 개선

- Tutor 전용 평가 모델 분리
- 권한별 통합 테스트 확대
- 비동기 작업 / 알림
- Seed 편성 결과의 통계적 균형 지표 시각화
- 운영 로그 및 감사 추적 강화
