# AX 수강생 평가 · 자동 팀 편성 시스템

Django + PostgreSQL 기반의 **수강생 평가, 결과 관리, 튜터 평가, Seed 기반 자동 팀 편성, 역량 성장 관리** 통합 프로젝트입니다.

이 프로젝트의 핵심은 단순 점수 기록이 아니라 다음 운영 흐름을 하나로 연결하는 것입니다.

```text
수강생 등록
→ 평가 회차·기본 과제 운영
→ 학생 팀 평가 / 동료 개인 평가 / 튜터 팀 평가
→ 결과·순위 계산
→ 관리자 보정 및 결과 공개
→ 누적 Seed 계산
→ 다음 회차 자동 팀 편성
→ 공통 역량 및 개별 성장 과제 관리
```

---

## 1. 프로젝트 핵심

### 평가 결과를 다음 팀 편성까지 연결

평가가 한 회차에서 끝나지 않고 다음 프로젝트의 팀 구성으로 이어집니다.

- 학생이 다른 팀을 평가
- 같은 팀원이 개인을 평가
- 튜터가 각 팀을 별도로 평가
- 세 평가 결과를 가중치로 합산
- 최종 결과를 다음 회차의 Seed로 활용
- Seed를 이용해 새로운 팀을 자동 편성

신규 회차 권장 가중치:

```text
학생 팀 평가 40%
동료 개인 평가 30%
튜터 팀 평가 30%
```

기존 데이터처럼 튜터 평가가 없던 회차는 40:60 등 기존 가중치도 유지할 수 있습니다.

### 실제 데이터 예외 처리

AX2 익명화 평가 데이터를 이관하면서 다음과 같은 실제 데이터 품질 문제를 처리합니다.

- 중복 응답
- 일부 결측 점수
- 같은 별칭이 서로 다른 팀에 등장하는 경우
- 자기 팀 평가처럼 시스템 규칙상 제외해야 하는 응답
- 원본 응답과 계산용 데이터의 기준 차이

원본은 임의 삭제하지 않고 **raw archive**에 보존하고, 화면·집계에는 규칙을 적용한 canonical 데이터를 사용합니다.

```text
원본 CSV
  ↓
raw archive 보존
  ↓
식별 / 중복 / 소속 / 평가 규칙 적용
  ↓
canonical 평가 데이터
  ↓
결과 계산 / 미제출 판정 / Seed 계산
```

AX2 기준 원본은 개인평가 101건 + 팀평가 66건, 총 167건입니다.

---

## 2. 주요 기능

### 수강생 관리

- 수강생 등록·수정·비활성화·삭제
- Excel 일괄 등록 / 내보내기
- 이메일 선택 입력
- 이메일이 없는 관리용 수강생 계정 생성
- 내부 username 자동 생성
- 비밀번호 초기화
- 이름 / 팀 / 평가 상태 검색 및 필터
- 수강생별 평가 결과, 배지, 역량 프로필 확인
- 관리자 피드백 및 개인 메시지

### 평가 회차와 기본 과제

- 평가 회차 생성 / 수정 / 삭제
- 현재 회차 지정
- 시작 전 / 진행 중 / 종료 상태 관리
- 평가 시작 / 중단 / 재개
- 팀 과제 / 개인 과제 등록
- 과제 첨부파일
- 팀·개인 제출 관리
- 평가 템플릿 재사용
- 발표 당일 출결에 따른 평가 권한 처리
- 평가 시작 전 필수 조건 점검

### 학생 팀 평가 / 동료 개인 평가

핵심 비즈니스 규칙은 `docs/templates/01_requirements/`의 BR-01 ~ BR-10을 기준으로 합니다.

주요 규칙:

- 자신의 팀은 팀 평가할 수 없음
- 다른 팀 구성원은 개인 평가할 수 없음
- 같은 팀 구성원만 개인 평가 가능
- 자기 자신은 개인 평가할 수 없음
- 동일 평가자의 동일 대상 중복 평가 금지
- 팀 점수는 다른 팀에게 받은 평가 기반
- 개인 점수는 같은 팀 구성원에게 받은 평가 기반
- 제출 완료된 평가만 결과 집계에 사용
- 결석 / 예외 출결은 평가 필요량 계산에 반영
- 결과는 다음 회차 자동 팀 편성 Seed에 반영

### 튜터 팀 평가

튜터는 학생 팀 평가와 같은 문항을 이용해 각 팀을 **1~5점 척도**로 평가할 수 있습니다.

- 팀 단위 1~5점 평가
- 팀별 튜터 코멘트
- 여러 튜터 평가 지원
- 팀별 튜터 평균 계산
- 튜터 비중이 있는 회차는 튜터 평가를 최종점수에 반영
- 저장 후 결과 재계산

### 결과·순위·관리자 보정

- 팀 평균점수
- 개인 평균점수
- 튜터 팀 평균점수
- 가중치 기반 최종점수
- 순위 계산
- 결과 공개 / 비공개 / 예약 공개
- 관리자 보정점수 입력
- 원 평가점수와 관리자 보정값 별도 보존
- 0이 아닌 보정값은 사유 필수
- 집계 제외 처리
- 평가 패턴 점검
- Excel 결과 내보내기

### 배지

- **MVP**: 현재 회차 최종 1위
- **성장왕**: 이전 회차 대비 순위 상승폭이 가장 큰 수강생
- **연속 우수**: 이전·현재 회차 모두 상위 3위

---

## 3. 자동 팀 편성

자동 편성은 바로 DB에 확정하지 않고 **조건 설정 → 미리보기 → 검토 → 확정** 흐름으로 동작합니다.

관리자는 다음 조건을 조절할 수 있습니다.

- 활성 수강생 수 확인
- 예정 팀 수 조절
- 편성 방식 선택
- 직전 팀원 중복 최소화 옵션
- FIFA 포트 경계값 직접 조절
- Seed가 없는 학생의 랜덤 배치

현재 세 가지 편성 방식을 지원합니다.

### 3-1. Z식(Snake) 성적 균형

Seed 순위를 기준으로 팀을 왕복하며 배치합니다.

```text
1 → 2 → 3 → 4
8 ← 7 ← 6 ← 5
9 → 10 → 11 → 12
```

장점:

- 상위 Seed가 특정 팀에 몰리는 현상을 강하게 억제
- Seed 보유자가 적은 상황에서도 비교적 안정적인 균형
- 결과와 배정 원리를 설명하기 쉬움

단점:

- Seed 없는 학생은 랜덤 요소가 남음
- 이전 성과가 다음 팀 구성에 직접 반영됨

현재 프로젝트에서는 **팀 간 Seed 균형을 최우선할 때 권장하는 방식**입니다.

### 3-2. FIFA 포트 추첨

Seed 순위를 A/B/C/D 포트로 나눈 뒤 각 포트 학생을 팀에 분산합니다.

기본 누적 경계:

```text
A 0~20%
B 20~50%
C 50~80%
D 80~100%
```

- A/B/C 포트의 누적 경계값을 직접 조절 가능
- 포트별 인원 현황 표시
- 팀별 포트 분산 상태 표시
- 특정 팀으로 포트가 치우치면 경고 표시

장점:

- 상·중·하위 그룹을 직관적으로 섞을 수 있음
- 스포츠 드래프트와 비슷해 설명이 쉬움
- 포트 경계를 운영자가 직접 조절 가능

단점:

- Seed 보유자 수와 팀 수가 맞지 않으면 포트 불균형 발생 가능
- 경계 설정에 따라 결과 편차가 달라질 수 있음

### 3-3. 균등 랜덤

활성 수강생을 무작위로 섞은 뒤 팀별 인원 차이가 최소가 되도록 배정합니다.

장점:

- 가장 단순하고 중립적
- 첫 회차처럼 Seed가 없을 때 적합
- 매번 다른 조합 생성 가능

단점:

- 실력 분포 균형을 보장하지 않음
- 상위권이 우연히 한 팀에 몰릴 수 있음

### 세 방식 비교

| 방식 | 균형성 | 무작위성 | 설명 용이성 | Seed 부족 상황 | 추천 상황 |
|---|---:|---:|---:|---:|---|
| Z식 | 높음 | 중간 | 높음 | 비교적 안정적 | 이전 성과를 반영한 균형 편성 |
| FIFA 포트 | 중~높음 | 중간 | 높음 | 포트 불균형 가능 | 등급별 분산을 명시적으로 관리 |
| 균등 랜덤 | 보장 없음 | 높음 | 매우 높음 | 영향 없음 | 첫 회차 / Seed 없음 |

---

## 4. Seed와 누적 성과

Seed는 이전 회차 결과를 다음 회차 팀 편성에 활용하기 위한 지표입니다.

- 이전 평가 결과 기반
- 회차별 가중치 적용 가능
- 오래된 프로젝트의 영향도를 낮출 수 있음
- 평가 결과가 없는 학생은 `Seed 없음`으로 표시
- Seed 없는 학생은 편성 과정에서 랜덤 요소로 처리

즉, `평가 → 결과 → Seed → 다음 팀 편성`의 연속적인 운영 구조를 지원합니다.

---

## 5. 역량 성장 관리

### 공통 역량 설정

관리자가 `Python`, `SQL`, `데이터 분석`, `발표`, `협업` 같은 공통 역량을 정의합니다.

- 새 공통 역량 생성 시 활성 수강생 전체에 자동 적용
- 초기 점수 0점
- 신규 수강생 등록 시 기존 공통 역량 자동 생성
- Excel 신규 등록에도 동일 적용
- 누락 역량 일괄 동기화
- 튜터가 학생별 점수 직접 수정 가능
- 사용 중인 역량은 삭제 보호

### 기본 과제 → 역량 반영

회차 기본 과제에 필요한 역량과 가중치를 지정할 수 있습니다.

```text
데이터 분석 과제
Python        40%
SQL           30%
데이터 분석   30%
```

가중치 합계는 100%이며 평가 성과를 역량 프로필에 반영할 수 있습니다.

### 개별 성장 과제

특정 수강생에게 별도 성장 과제를 줄 수 있습니다.

- 과제명
- 담당 수강생
- 설명
- 시작일 / 마감일
- 상태 / 우선순위
- 연결 평가 회차
- 필요 역량 및 가중치
- 관리자 첨부파일
- 수행 단계와 상세 지시사항
- 학생 자기진도 체크
- 결과물 제출
- 튜터 검토 및 0~100점 평가
- 역량 점수 반영

### 수행 흐름

```text
단계 확인
→ 학생 자기진도 체크
→ 결과물 제출
→ 관리자/튜터 검토
→ 0~100점 평가
→ 최종 완료
→ 역량 점수 반영
```

---

## 6. 관리자 화면

관리자는 한 시스템에서 다음 업무를 처리합니다.

- 운영 대시보드
- 수강생 관리
- 팀 관리 / 자동 편성
- 평가 회차 관리
- 팀·개인 과제 관리
- 평가 템플릿 / 문항 관리
- 누락 평가 확인
- 튜터 팀 평가
- 팀 / 개인 / 최종 점수 확인
- 결과 공개 설정
- 관리자 보정
- Seed 관리
- 출결 관리
- 공통 역량 / 성장 과제 관리
- 공지 / 개인 메시지
- 활동 로그
- 데이터 관리

관리자 홈에는 현재 회차, 수강생·팀 현황, 평가 완료율, 기본 과제, 확인이 필요한 성장 과제 등을 요약합니다.

---

## 7. 수강생 화면

- 현재 회차 및 평가 상태
- 소속 팀 정보
- 기본 과제 확인 / 제출
- 팀 평가
- 개인 평가
- 평가 진행 현황
- 공개된 결과 및 배지
- 자기 성찰
- 공지 / 개인 메시지
- 역량 프로필
- 내 성장 과제
- Step 상세 지시사항
- 관리자 첨부파일 다운로드
- 결과물 제출 및 튜터 평가 확인

---

## 8. 요구사항과 핵심 비즈니스 규칙

초기 요구사항과 세부 문서는 `docs/templates/` 아래에 보존합니다.

주요 규칙:

| 구분 | 규칙 |
|---|---|
| 팀 평가 | 자신의 팀 평가 금지 |
| 개인 평가 | 같은 팀원만 평가 가능 |
| 자기 평가 | 자기 자신 평가 금지 |
| 중복 평가 | 동일 평가자·동일 대상 중복 금지 |
| 팀 점수 | 타 팀 학생 평가 기반 |
| 개인 점수 | 동 팀원 평가 기반 |
| 튜터 점수 | 튜터가 팀 단위로 별도 평가 |
| 최종 점수 | 회차별 가중치 정책에 따라 계산 |
| 결과 확정 | 평가 완료 상태와 운영 조건을 반영 |
| 다음 회차 | 결과를 Seed로 사용 가능 |

상세 문서:

- 요구사항 / BR-01 ~ BR-10: `docs/templates/01_requirements/`
- DB / ERD: `docs/templates/02_data/`
- 사용자 흐름: `docs/templates/04_scenarios/`
- UI 기준: `docs/templates/05_ui/`
- 테스트 기준: `docs/templates/06_test/`

---

## 9. 프로젝트 구조

리팩터링 이후 비즈니스 로직을 View에 집중시키지 않고 Service 계층으로 분리했습니다.

```text
URL
 ↓
View
 ↓
Service
 ↓
Model / Query
```

현재 주요 구조:

```text
config/                         Django 프로젝트 설정
├─ settings.py
├─ urls.py
├─ asgi.py
└─ wsgi.py

dashboard/                      핵심 서비스 앱
├─ models.py                     DB 모델
├─ forms.py                      입력 검증
├─ urls.py                       URL 라우팅
├─ adapters.py                   OAuth 계정 연결 정책
├─ middleware.py                 관리자 활동 로그 등
├─ context_processors.py         공통 알림 데이터
│
├─ views/                        요청/응답 처리
│  ├─ auth.py
│  ├─ student_core.py
│  ├─ student_assignments.py
│  ├─ student_evaluations.py
│  ├─ student_results.py
│  ├─ student_account.py
│  ├─ student_hr.py
│  ├─ admin_home.py
│  ├─ admin_operations.py
│  ├─ admin_student_list.py
│  ├─ admin_student_crud.py
│  ├─ admin_student_detail.py
│  ├─ admin_student_excel.py
│  ├─ admin_student_messages.py
│  ├─ admin_skills.py
│  ├─ admin_team_management.py
│  ├─ admin_team_assignment.py
│  ├─ admin_team_assignment_configurable.py
│  ├─ admin_rounds.py
│  ├─ admin_round_lifecycle.py
│  ├─ admin_assignments.py
│  ├─ admin_evaluations.py
│  ├─ admin_tutor.py
│  ├─ admin_results.py
│  ├─ admin_scores.py
│  ├─ admin_missing.py
│  ├─ admin_result_settings.py
│  ├─ admin_result_adjustments.py
│  ├─ admin_result_export.py
│  ├─ admin_seed.py
│  ├─ admin_hr_tasks.py
│  ├─ admin_hr_dashboard.py
│  └─ admin_system.py
│
├─ services/                     비즈니스 로직
│  ├─ admin_dashboard_service.py
│  ├─ assignment_service.py
│  ├─ evaluation_completion_service.py
│  ├─ evaluation_results_service.py
│  ├─ missing_evaluations_service.py
│  ├─ official_import_service.py
│  ├─ result_adjustment_service.py
│  ├─ result_export_service.py
│  ├─ result_publication_service.py
│  ├─ result_service.py
│  ├─ result_support_service.py
│  ├─ round_lifecycle_service.py
│  ├─ score_read_service.py
│  ├─ scoring_policy.py
│  ├─ seed_service.py
│  ├─ team_assignment_service.py
│  └─ tutor_evaluation_service.py
│
├─ management/commands/          데이터·운영 관리 명령
│  ├─ prepare_postgres.py
│  ├─ rebuild_ax2_corrected.py
│  ├─ audit_ax2_consistency.py
│  ├─ reset_and_import_ax2_data.py
│  ├─ reset_and_import_ax2_data_v2.py
│  └─ ...
│
├─ templates/
│  ├─ admin_ui/
│  ├─ student/
│  └─ common/
│
└─ migrations/

static/
├─ css/
└─ js/

media/                           사용자 업로드 파일
docs/                            요구사항·설계·가이드·테스트 문서
tools/                           로컬 실행/점검/데모 보조 스크립트
.github/workflows/               GitHub Actions CI

manage.py
requirements.txt
.env.example
```

대형 legacy View를 기능별 View와 Service로 나누어 유지보수성과 테스트 가능성을 높였습니다.

---

## 10. 설치

### 1) 가상환경

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

PowerShell 실행 정책 때문에 막히면 현재 터미널에서만:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 2) 패키지 설치

```powershell
pip install -r requirements.txt
```

주요 의존성:

- Django
- django-allauth
- python-dotenv
- psycopg
- openpyxl

### 3) 환경변수

`.env.example`을 참고해 `.env`를 설정합니다.

```env
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=...
DB_HOST=127.0.0.1
DB_PORT=5432
DB_SCHEMA=practice
```

OAuth 사용 시 Google / Kakao Client ID와 Secret도 `.env`에 설정합니다.

> `.env`에는 실제 비밀번호와 OAuth Secret이 들어갈 수 있으므로 Git에 커밋하지 않습니다.

---

## 11. DB 준비와 실행

처음 구성하는 경우:

```powershell
python manage.py prepare_postgres
python manage.py migrate
python manage.py check
```

개발 서버:

```powershell
python manage.py runserver
```

같은 네트워크에서 테스트:

```powershell
python manage.py runserver 0.0.0.0:8000
```

기본 주소:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/management/
```

---

## 12. AX2 데이터 이관 및 검증

### Dry-run

DB를 변경하지 않고 먼저 입력 구조를 확인합니다.

```powershell
python manage.py rebuild_ax2_corrected .\data\ax2_personal.csv .\data\ax2_team.csv
```

### 실제 반영

```powershell
python manage.py rebuild_ax2_corrected .\data\ax2_personal.csv .\data\ax2_team.csv --apply
```

`--apply` 실행 시 dashboard 업무 데이터를 초기화하고 데이터를 다시 구성합니다. staff / superuser 계정은 보존합니다.

### 일관성 감사

```powershell
python manage.py audit_ax2_consistency
```

검사 대상:

- 학생 / 팀 배정 일관성
- 중복 팀 배정
- 평가 필요량과 실제 제출량
- 자기 팀 평가
- 개인평가 대상 규칙
- 결과 건수
- 평가 템플릿 / 문항
- raw archive
- 표시명 충돌

---

## 13. 파일 및 데이터 관리

### media 폴더

`media/`에는 과제·제출물 등 실제 업로드 파일이 저장됩니다.

DB가 참조하지 않는 orphan 파일만 정리하도록 구성하며 다음 파일은 보호 대상입니다.

- 기본 과제 첨부파일
- 팀 제출 첨부파일
- 개인 제출 첨부파일
- 성장 과제 관리자 첨부파일
- 성장 과제 학생 제출 첨부파일

### 성장 과제 삭제

성장 과제를 삭제할 경우 연결된 Step, 필요 역량, 제출·평가·반영 기록 및 관련 업로드 파일을 함께 정리합니다.

---

## 14. 테스트와 CI

로컬 기본 확인:

```powershell
python manage.py check
python manage.py test dashboard
```

구조 검증 테스트에서는 Service가 View를 역참조하지 않는지, 주요 URL callback이 callable인지, 삭제된 legacy View가 다시 생기지 않는지 등을 점검합니다.

GitHub Actions도 추가되어 push / pull request 시 Django check와 핵심 테스트를 자동 실행하도록 구성했습니다.

---

## 15. 문서 위치

- 최초 요구사항 / BR-01 ~ BR-10: `docs/templates/01_requirements/`
- DB / ERD 기준: `docs/templates/02_data/`
- 사용자 흐름: `docs/templates/04_scenarios/`
- UI 기준: `docs/templates/05_ui/`
- 테스트 기준: `docs/templates/06_test/`
- 로컬 실행: `docs/guides/LOCAL_RUN_GUIDE.md`
- PostgreSQL 설정: `docs/guides/POSTGRESQL_SETUP.md`
- OAuth 설정: `docs/guides/OAUTH_SETUP.md`
- 현재 구조: `docs/guides/PROJECT_STRUCTURE.md`

---

## 16. 프로젝트에서 해결한 핵심 문제

| 문제 | 해결 방식 |
|---|---|
| 평가 결과가 한 번 쓰이고 끝남 | 결과를 Seed로 연결해 다음 팀 편성에 재사용 |
| 랜덤 편성의 실력 편차 | Z식 / FIFA 포트 / 균등 랜덤 제공 |
| 한 가지 알고리즘만으로 운영 상황 대응 어려움 | 세 방식 미리보기 후 관리자 선택·확정 |
| 실제 CSV에 중복·결측·소속 충돌 존재 | raw 보존 + canonical 데이터 분리 |
| 튜터 평가와 학생 평가 구분 필요 | 튜터 팀 평가를 별도 집계해 가중치 적용 |
| 미제출 평가가 평균을 왜곡 | 완료 평가자 집합 기준으로 집계 |
| 결과 공개 시점 통제 필요 | 공개 / 비공개 / 예약 공개 |
| 거대한 View 파일 유지보수 문제 | 기능별 View + Service 계층으로 리팩터링 |

---

## 17. 향후 개선

- Tutor 전용 평가 모델 분리
- 권한별 통합 테스트 확대
- 자동 팀 편성 결과의 통계적 균형 지표 추가
- 운영 로그 / 감사 추적 강화
- 비동기 알림 및 작업 처리

---

## 요약

이 프로젝트는 **평가 → 결과 → Seed → 다음 팀 편성**을 하나의 사이클로 연결하고, 그 위에 **튜터 평가, 결과 공개, 관리자 보정, 실제 CSV 정제, 역량 성장 관리**를 결합한 교육 운영 시스템입니다.

단순 CRUD 구현보다 실제 운영 규칙과 데이터 예외를 시스템에 반영하고, `URL → View → Service → Model` 구조로 기능을 분리해 지속적으로 확장할 수 있도록 구성하는 것을 목표로 합니다.
