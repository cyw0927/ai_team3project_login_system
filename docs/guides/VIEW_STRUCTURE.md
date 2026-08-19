# View 구조

기존 단일 `dashboard/views.py`를 아래처럼 분리했습니다.

- `common.py` — 공통 helper, 권한 decorator, 계산 함수
- `auth.py` — 로그인 / 로그아웃
- `student.py` — 학생 기능
- `admin_dashboard.py` — 관리자 홈 / 운영 / 출결
- `admin_students.py` — 수강생 관리
- `admin_rounds.py` — 회차 / 과제
- `admin_teams.py` — 팀 / 자동 편성
- `admin_evaluations.py` — 평가 / 결과 / 점수 / 순위 / Seed
- `admin_system.py` — 공지 / 로그 / 데이터 백업·복구
- `errors.py` — 오류 handler

`dashboard/urls.py`의 외부 API는 그대로 유지합니다.
