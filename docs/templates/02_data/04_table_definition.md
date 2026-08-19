# 테이블 정의서 — 실제 Django 모델 기준

## 핵심 테이블

### STUDENT
- user_id: auth_user OneToOne
- is_active
- major

### EVALUATION_ROUND
- name
- start_at / end_at
- status: scheduled / in_progress / ended
- evaluation_started
- is_locked
- personal_weight
- team_weight

### ASSIGNMENT
- evaluation_round_id: OneToOne
- title / description / attachment

### TEAM
- evaluation_round_id
- name
- project_title
- is_active
- UNIQUE(evaluation_round, name)

### TEAM_MEMBERSHIP
- team_id
- student_id
- is_leader
- UNIQUE(team, student)
- 추가 서버 검증: 동일 학생 동일 회차 복수 팀 소속 금지

### TEAM_ASSIGNMENT_SUBMISSION
- assignment_id
- team_id
- submitted_by_id
- submission_url / attachment / note
- admin_comment / commented_by_id / commented_at
- submitted_at
- UNIQUE(assignment, team)

### EVALUATION_TEMPLATE / EVALUATION_CRITERION
- 팀/개인 템플릿 및 문항

### TEAM_EVALUATION
- evaluation_round_id
- evaluator_id
- target_team_id
- comment
- is_submitted
- submitted_at
- UNIQUE(evaluation_round, evaluator, target_team)

### TEAM_EVALUATION_SCORE
- evaluation_id
- criterion_id
- score: 1~5
- UNIQUE(evaluation, criterion)

### PERSONAL_EVALUATION
- evaluation_round_id
- evaluator_id
- target_student_id
- comment
- is_submitted
- submitted_at
- UNIQUE(evaluation_round, evaluator, target_student)

### PERSONAL_EVALUATION_SCORE
- evaluation_id
- criterion_id
- score: 1~5
- UNIQUE(evaluation, criterion)

### ROUND_ATTENDANCE
- evaluation_round_id
- student_id
- status
- note
- UNIQUE(evaluation_round, student)

### TEAM_RESULT
- evaluation_round_id
- team_id
- score
- rank
- is_excluded
- UNIQUE(evaluation_round, team)

### STUDENT_RESULT
- evaluation_round_id
- student_id
- team_score
- personal_score
- base_score
- adjustment_score
- adjustment_reason
- final_score
- rank
- is_excluded
- UNIQUE(evaluation_round, student)

### RESULT_PUBLISH_SETTING
- evaluation_round_id: OneToOne
- is_published
- publish_at
- show_team_first_place
- show_all_team_ranks
- show_personal_score
- show_overall_rank
- show_comments

## 자동편성 시드

별도 테이블을 만들지 않습니다.

```text
ENDED EvaluationRound
→ StudentResult.final_score
→ 학생별 누적 평균
→ 자동 팀 편성
```
