# 프로그램 목록 초안

| 프로그램 ID | 프로그램명 | 사용자 | 목적 | 예상 URL | 관련 BR/RFP | UI 필요 | 상태 |
|---|---|---|---|---|---|---|---|
| PG-01 | 로그인 | 전체 | 사용자 인증 | /accounts/login/ | RFP 6 | O | 설계 |
| PG-02 | 학생 홈 | 학생 | 현재 과제·팀·평가 상태 확인 | /student/ | RFP 5,19 | O | 설계 |
| PG-03 | 현재 팀 조회 | 학생 | 현재 회차 팀과 팀원 확인 | /student/team/ | RFP 5,19 | O | 설계 |
| PG-04 | 과제 정보 조회 | 학생 | 현재 과제와 평가 일정 확인 | /student/assignment/ | RFP 7,19 | O | 설계 |
| PG-05 | 팀 평가 대상 목록 | 학생 | 본인 팀을 제외한 평가 가능 팀 조회 | /evaluations/team/ | BR-01,05 | O | 설계 |
| PG-06 | 팀 평가 입력/제출 | 학생 | 다른 팀 평가 제출 | /evaluations/team/<team_id>/ | BR-01,05,06 | O | 설계 |
| PG-07 | 개인 평가 대상 목록 | 학생 | 같은 팀 + 본인 제외 대상 조회 | /evaluations/peer/ | BR-02~05 | O | 설계 |
| PG-08 | 개인 평가 입력/제출 | 학생 | 같은 팀원 개인 평가 제출 | /evaluations/peer/<student_id>/ | BR-02~05,07 | O | 설계 |
| PG-09 | 평가 제출 현황 | 학생 | 완료/미완료 평가 확인 | /evaluations/status/ | BR-05, RFP 19 | O | 설계 |
| PG-10 | 학생 결과 조회 | 학생 | 공개 허용된 점수·순위 확인 | /results/ | BR-08,10 | O | 설계 |
| PG-11 | 수강생 관리 | 관리자 | 수강생 목록/상태 관리 | /admin/ 또는 /dashboard/students/ | RFP 5.2 | 선택 | 설계 |
| PG-12 | 평가 회차 관리 | 관리자 | 회차 생성/수정/상태 관리 | /dashboard/rounds/ | RFP 7 | O | 설계 |
| PG-13 | 과제 관리 | 관리자 | 회차별 과제 등록/수정 | /dashboard/assignments/ | RFP 7 | O | 설계 |
| PG-14 | 수동 팀 편성 | 관리자 | 학생을 직접 팀에 배정 | /dashboard/teams/manual/ | BR-09, RFP 8 | O | 설계 |
| PG-15 | 자동 팀 편성 | 관리자 | 누적 시드 기반 자동 편성 | /dashboard/teams/auto/ | BR-09 | O | 설계 |
| PG-16 | 팀 구성 수정 | 관리자 | 자동/수동 편성 결과 수정 | /dashboard/teams/ | BR-09, RFP 8 | O | 설계 |
| PG-17 | 평가 템플릿 관리 | 관리자 | 팀/개인 평가 문항 관리 | /dashboard/templates/ | RFP 9,10 | O | 설계 |
| PG-18 | 평가 시작/종료 | 관리자 | 평가 진행 상태 제어 | /dashboard/rounds/<id>/ | RFP 5.2,7 | O | 설계 |
| PG-19 | 팀 점수/순위 계산 | 관리자/시스템 | 타 팀 평가 기반 팀점수 및 순위 산출 | /dashboard/results/team/ | BR-06 | O | 설계 |
| PG-20 | 개인점수 계산 | 관리자/시스템 | 같은 팀 상호평가 기반 개인점수 산출 | /dashboard/results/personal/ | BR-07 | O | 설계 |
| PG-21 | 최종점수/개인 석차 계산 | 관리자/시스템 | 40:60 최종점수 및 전체 석차 산출 | /dashboard/results/final/ | BR-08 | O | 설계 |
| PG-22 | 결과 공개 설정 | 관리자 | 4개 결과 항목 공개/비공개 설정 | /dashboard/results/visibility/ | BR-10 | O | 설계 |
| PG-23 | 누적 시드 관리 | 관리자/시스템 | 개인 최종점수를 다음 편성 시드로 저장 | /dashboard/seeds/ | BR-09 | O | 설계 |
| PG-24 | 전체 평가 결과 조회 | 관리자 | 공개 여부와 무관하게 전체 결과 확인 | /dashboard/results/ | BR-06~10 | O | 설계 |
