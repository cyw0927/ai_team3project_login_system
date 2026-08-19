# ERD 명세 — 실제 구현 기준

> 최종 Django `dashboard/models.py`를 기준으로 재검증한 데이터 설계입니다.

## 중요 보정

- 실제 구현에는 별도 `TeamSeed` 모델이 없습니다.
- 자동편성 시드는 이전 **종료 회차**의 `StudentResult.final_score`를 학생별 누적 평균하여 계산합니다.
- 평가 문항 응답은 공통 `EVALUATION_RESPONSE`가 아니라 `TeamEvaluationScore`와 `PersonalEvaluationScore`로 분리되어 있습니다.

## 실제 엔터티

| 논리 엔터티 | Django 모델 | 목적 |
|---|---|---|
| 사용자 | `auth.User` | 로그인/권한 |
| 학생 | `Student` | 수강생 프로필 |
| 평가 회차 | `EvaluationRound` | 회차/상태/가중치 |
| 과제 | `Assignment` | 회차별 과제 |
| 팀 | `Team` | 회차별 팀 |
| 팀 구성 | `TeamMembershipship` | 학생-팀 관계 |
| 팀 과제 제출 | `TeamAssignmentSubmission` | 팀 제출물 |
| 평가 템플릿 | `EvaluationTemplate` | 팀/개인 평가 템플릿 |
| 평가 문항 | `EvaluationCriterion` | 평가 문항 |
| 팀 평가 | `TeamEvaluation` | 평가자→팀 |
| 팀 문항 점수 | `TeamEvaluationScore` | 팀 평가 문항별 점수 |
| 개인 평가 | `PersonalEvaluation` | 평가자→학생 |
| 개인 문항 점수 | `PersonalEvaluationScore` | 개인 평가 문항별 점수 |
| 회차 출결 | `RoundAttendance` | 발표 당일 출결 |
| 팀 결과 | `TeamResult` | 팀 점수/순위 |
| 학생 결과 | `StudentResult` | 팀/개인/최종점수/석차 |
| 결과 공개 | `ResultPublishSetting` | 공개 범위 |
| 공지 | `Announcement` | 공지 |
| 공지 읽음 | `AnnouncementRead` | 학생별 읽음 |
| 관리자 로그 | `AdminActivityLog` | 감사 로그 |

## 핵심 관계

- User 1:0..1 Student
- EvaluationRound 1:1 Assignment
- EvaluationRound 1:N Team
- Team 1:N TeamMembershipship
- Student 1:N TeamMembershipship
- Assignment 1:N TeamAssignmentSubmission
- EvaluationRound 1:N EvaluationTemplate
- EvaluationTemplate 1:N EvaluationCriterion
- EvaluationRound 1:N TeamEvaluation
- TeamEvaluation 1:N TeamEvaluationScore
- EvaluationRound 1:N PersonalEvaluation
- PersonalEvaluation 1:N PersonalEvaluationScore
- EvaluationRound 1:N TeamResult
- EvaluationRound 1:N StudentResult
- EvaluationRound 1:1 ResultPublishSetting

## BR-09 실제 데이터 흐름

```text
종료된 이전 회차의 StudentResult.final_score
→ 학생별 Avg(final_score)
→ 누적 시드
→ Z(스네이크) 자동 팀 편성
→ 관리자 Preview
→ Confirm
```

`누적 시드`는 별도 저장 테이블이 아니라 `StudentResult`에서 계산하는 파생값입니다.
