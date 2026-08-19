# 상세 정상/예외 시나리오

| 단계 | 사용자 행동 | 시스템 처리 | 관련 테이블/컬럼 | BR |
|---|---|---|---|---|
| 1 | 학생이 팀 평가 메뉴 선택 | 현재 회차 확인 | EVALUATION_ROUND.status | BR-01,05 |
| 2 | 대상 팀 선택 | 학생의 팀 조회 | TEAM_MEMBERSHIP.student_id/team_id | BR-01 |
| 3 | 평가하기 클릭 | 본인 팀과 대상 팀 비교 | TEAM.team_id | BR-01 |
| 4 | 문항 입력 | 1~5점 범위 검증 | EVALUATION_CRITERION, RESPONSE.score | BR-06 |
| 5 | 제출 | 기존 평가 조회 | TEAM_EVALUATION | BR-05 |
| 6 | - | 평가/응답 저장 | TEAM_EVALUATION, TEAM_EVALUATION_SCORE | BR-01,05,06 |

## 팀 평가 예외

| 단계 | 예외 조건 | 시스템 처리 | 관련 테이블/컬럼 | BR |
|---|---|---|---|---|
| 1 | 대상 팀 = 본인 팀 | 저장 차단 | TEAM_MEMBERSHIP, TEAM | BR-01 |
| 2 | 기존 평가 존재 | 신규 저장 차단 | TEAM_EVALUATION unique key | BR-05 |
| 3 | 평가 종료 | 제출 차단 | EVALUATION_ROUND.status | BR-05 |
| 4 | 점수 1~5 범위 밖 | 저장 차단 | RESPONSE.score | BR-06 |

## 개인 평가 정상

| 단계 | 사용자 행동 | 시스템 처리 | 관련 테이블/컬럼 | BR |
|---|---|---|---|---|
| 1 | 개인 평가 메뉴 선택 | 같은 팀원 조회 | TEAM_MEMBERSHIP | BR-02,03 |
| 2 | 팀원 선택 | 본인 제외 확인 | STUDENT.student_id | BR-04 |
| 3 | 평가하기 클릭 | 같은 팀 여부 재검증 | TEAM_MEMBERSHIP | BR-02,03 |
| 4 | 문항 입력 | 1~5점 범위 검증 | EVALUATION_CRITERION, RESPONSE.score | BR-07 |
| 5 | 제출 | 기존 평가 조회 | PERSONAL_EVALUATION | BR-05 |
| 6 | - | 평가/응답 저장 | PERSONAL_EVALUATION, PERSONAL_EVALUATION_SCORE | BR-03,05,07 |

## 개인 평가 예외

| 단계 | 예외 조건 | 시스템 처리 | 관련 테이블/컬럼 | BR |
|---|---|---|---|---|
| 1 | 다른 팀 학생 | 차단 | TEAM_MEMBERSHIP | BR-02 |
| 2 | 자기 자신 | 차단 | evaluator_student_id, target_student_id | BR-04 |
| 3 | 기존 평가 존재 | 신규 저장 차단 | PERSONAL_EVALUATION unique key | BR-05 |
| 4 | 평가 종료 | 제출 차단 | EVALUATION_ROUND.status | BR-05 |
