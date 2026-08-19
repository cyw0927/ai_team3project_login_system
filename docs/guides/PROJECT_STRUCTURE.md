# 현재 프로젝트 구조

프로젝트는 하나의 `dashboard` 앱을 중심으로 유지합니다.

```text
dashboard/
├─ models.py
├─ urls.py
├─ views/
│  ├─ auth.py
│  ├─ student.py
│  ├─ admin_dashboard.py
│  ├─ admin_students.py
│  ├─ admin_rounds.py
│  ├─ admin_teams.py
│  ├─ admin_evaluations.py
│  ├─ admin_system.py
│  ├─ admin_hr_tasks.py
│  ├─ admin_hr_dashboard.py
│  └─ common.py
├─ templates/
└─ migrations/
```

화면에서는 `HR` 대신 **수강생 성장 / 역량 과제 / 역량 프로필** 용어를 사용합니다.
내부 `HRTask` 모델명은 기존 migration 및 DB 안정성을 위해 유지합니다.
