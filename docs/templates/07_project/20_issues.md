# 개발 Issue 초안

| Issue | Epic | 작업 | 관련 BR | Program | Scenario | UI | 주요 완료조건 |
|---|---|---|---|---|---|---|---|
| ISSUE-01 | EPIC-A | 로그인 및 역할 분기 | 공통 | PG-01 | - | UI-AUTH-01 | 로그인 성공/실패, 권한 분기 |
| ISSUE-02 | EPIC-B | 평가 회차 관리 | 공통 | PG-12,18 | Overall | UI-ADM-01 | 회차 CRUD, 상태 전환 |
| ISSUE-03 | EPIC-B | 과제 관리 | 공통 | PG-04,13 | Overall | UI-STU-03, UI-ADM-02 | 회차별 과제 등록/조회 |
| ISSUE-04 | EPIC-C | 팀 데이터/현재 팀 조회 | BR-01~04 | PG-03 | Overall | UI-STU-02 | 회차별 팀/팀원 확인 |
| ISSUE-05 | EPIC-C | 수동 팀 편성 | BR-09 | PG-14,16 | SC-SEED-01 | UI-ADM-03 | 학생 중복 배정 방지 |
| ISSUE-06 | EPIC-C | 누적 시드/자동 팀 편성 | BR-09 | PG-15,23 | SC-SEED-01 | UI-ADM-03 | 이전 결과 기반 균형 편성 |
| ISSUE-07 | EPIC-D | 평가 템플릿/문항 | BR-03,06,07 | PG-17 | Overall | UI-ADM-04 | TEAM/PEER, 1~5점 |
| ISSUE-08 | EPIC-E | 팀 평가 대상 목록 | BR-01,05 | PG-05 | SC-TEAM-01 | UI-TEAM-01 | 본인 팀 제외, 완료 표시 |
| ISSUE-09 | EPIC-E | 팀 평가 제출 | BR-01,05,06 | PG-06 | SC-TEAM-01~03 | UI-TEAM-02 | 서버 재검증, 중복 차단 |
| ISSUE-10 | EPIC-F | 개인 평가 대상 목록 | BR-02~05 | PG-07 | SC-PEER-01 | UI-PEER-01 | 같은 팀+본인 제외 |
| ISSUE-11 | EPIC-F | 개인 평가 제출 | BR-02~05,07 | PG-08 | SC-PEER-01~04 | UI-PEER-02 | 다른 팀/자기/중복 차단 |
| ISSUE-12 | EPIC-E/F | 평가 제출 현황 | BR-05 | PG-09 | - | UI-STATUS-01 | 대상별 완료 상태 |
| ISSUE-13 | EPIC-G | 팀 점수/순위 | BR-06 | PG-19 | SC-RESULT-01 | UI-ADM-05 | 유효 타 팀 평가 집계 |
| ISSUE-14 | EPIC-G | 개인점수 | BR-07 | PG-20 | SC-RESULT-01 | UI-ADM-05 | 같은 팀 평가 집계 |
| ISSUE-15 | EPIC-G | 최종점수/석차 | BR-08 | PG-21 | SC-RESULT-01 | UI-ADM-05 | 40:60, 전체 석차 |
| ISSUE-16 | EPIC-H | 결과 공개 설정 | BR-10 | PG-22 | SC-VIS-01 | UI-ADM-05 | 4개 항목 독립 설정 |
| ISSUE-17 | EPIC-H | 학생 결과 조회 | BR-08,10 | PG-10 | SC-VIS-01 | UI-RESULT-01 | 공개 데이터만 제공 |
| ISSUE-18 | EPIC-H | 관리자 전체 결과 | BR-06~10 | PG-24 | SC-VIS-01 | UI-ADM-05 | 공개 여부 무관 조회 |
| ISSUE-19 | EPIC-I | 테스트/검증 | BR-01~10 | 전체 | 전체 | 전체 | TC 실행 및 결과 기록 |
| ISSUE-20 | EPIC-I | 내부망 시연/README | 공통 | 전체 | Overall | - | 0.0.0.0:8000, 다른 PC 접속 |
