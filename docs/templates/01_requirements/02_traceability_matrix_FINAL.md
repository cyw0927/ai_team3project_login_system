# 요구사항 추적표 (설계 완료본)

| BR | 요구사항 | 주요 데이터 | 프로그램 | 시나리오 | UI | 개발 Issue | Test Case | 상태 |
|---|---|---|---|---|---|---|---|---|
| BR-01 | 자신의 팀 팀 평가 금지 | Team, TeamMembership, TeamEvaluation | PG-05,06 | SC-TEAM-01,02 | UI-TEAM-01,02 | ISSUE-08,09 | TC-TEAM-01,02 | 설계 완료 |
| BR-02 | 다른 팀 학생 개인 평가 금지 | TeamMembershipship, PersonalEvaluation | PG-07,08 | SC-PEER-01,03 | UI-PEER-01,02 | ISSUE-10,11 | TC-PEER-01,03 | 설계 완료 |
| BR-03 | 같은 팀원 개인 평가 허용 | TeamMembershipship, PersonalEvaluation, Response | PG-07,08 | SC-PEER-01 | UI-PEER-01,02 | ISSUE-10,11 | TC-PEER-01 | 설계 완료 |
| BR-04 | 자기 자신 개인 평가 금지 | PersonalEvaluation | PG-07,08 | SC-PEER-02 | UI-PEER-01,02 | ISSUE-10,11 | TC-PEER-02 | 설계 완료 |
| BR-05 | 동일 대상 중복 평가 금지 | TeamEvaluation, PersonalEvaluation | PG-05~09 | SC-TEAM-03, SC-PEER-04 | UI-TEAM/PEER/STATUS | ISSUE-08~12 | TC-TEAM-03, TC-PEER-04 | 설계 완료 |
| BR-06 | 타 팀 평가 기반 팀 점수 | TeamEvaluation, TeamResult | PG-19 | SC-RESULT-01 | UI-ADM-05 | ISSUE-13 | TC-RESULT-01 | 설계 완료 |
| BR-07 | 같은 팀 평가 기반 개인점수 | PersonalEvaluation, PersonalEvaluationScore, StudentResult | PG-20 | SC-RESULT-01 | UI-ADM-05 | ISSUE-14 | TC-RESULT-02 | 설계 완료 |
| BR-08 | 팀40%+개인60% 최종점수 | TeamResult, StudentResult | PG-21 | SC-RESULT-01 | UI-RESULT-01, UI-ADM-05 | ISSUE-15,17 | TC-RESULT-03, TC-RANK-01 | 설계 완료 |
| BR-09 | 최종점수의 다음 팀 편성 시드 활용 | StudentResult, TeamMembershipship | PG-14~16,23 | SC-SEED-01 | UI-ADM-03 | ISSUE-05,06 | TC-SEED-01~03, TC-TEAMMEM-01 | 설계 완료 |
| BR-10 | 결과 공개 여부 관리자 설정 | ResultPublishSetting, StudentResult | PG-10,22,24 | SC-VIS-01 | UI-RESULT-01, UI-ADM-05 | ISSUE-16~18 | TC-VIS-01~03 | 설계 완료 |

## RFP 추가 핵심 기능 추적

| 요구 | Program | UI/산출물 | Issue |
|---|---|---|---|
| 로그인 | PG-01 | UI-AUTH-01 | ISSUE-01 |
| 평가 회차 | PG-12,18 | UI-ADM-01 | ISSUE-02 |
| 과제 | PG-04,13 | UI-STU-03, UI-ADM-02 | ISSUE-03 |
| 수동/자동 팀 편성 | PG-14~16 | UI-ADM-03 | ISSUE-05,06 |
| 평가 템플릿 | PG-17 | UI-ADM-04 | ISSUE-07 |
| 개인 전체 석차 | PG-21 | UI-RESULT-01, UI-ADM-05 | ISSUE-15 |
| 내부망 시연 | 전체 | README/발표 검증 | ISSUE-20 |
