"""Build admin missing-evaluation rows and summary data."""

from dashboard.models import (
    PersonalEvaluation,
    RoundAttendance,
    Team,
    TeamEvaluation,
    TeamMembership,
)
from dashboard.services.official_import_service import official_response_counts


def build_missing_evaluations_data(
    selected_round,
    evaluation_type="all",
    query="",
    *,
    complete_team_evaluator_ids,
    complete_personal_evaluator_ids,
):
    rows = []
    summary = {
        "team_missing": 0,
        "personal_missing": 0,
        "draft_count": 0,
        "not_started_count": 0,
        "exempt_team_count": 0,
        "team_incomplete_evaluators": 0,
        "personal_incomplete_evaluators": 0,
        "partial_excluded_evaluators": 0,
    }

    query = (query or "").strip().lower()

    # 공식 CSV import 회차는 raw 응답 자체가 제출 완료 원본이다.
    # canonical 테이블의 unique 제약/소속 투영 때문에 생긴 가짜 미제출 조합을 만들지 않는다.
    official_counts = official_response_counts(selected_round)
    if official_counts:
        summary["total_missing"] = 0
        summary["official_import"] = True
        summary["official_team_responses"] = official_counts["team"]
        summary["official_personal_responses"] = official_counts["personal"]
        return {"rows": [], "summary": summary}

    if selected_round:
        memberships_qs = list(
            TeamMembership.objects.filter(
                team__evaluation_round=selected_round,
                team__is_active=True,
                student__is_active=True,
            )
            .select_related("team", "student__user")
            .order_by("student__user__first_name", "student__user__username")
        )

        active_teams = list(
            Team.objects.filter(evaluation_round=selected_round, is_active=True).order_by("name")
        )

        memberships_by_team = {}
        for membership in memberships_qs:
            memberships_by_team.setdefault(membership.team_id, []).append(membership)

        attendance_map = dict(
            RoundAttendance.objects.filter(
                evaluation_round=selected_round,
                student_id__in=[m.student_id for m in memberships_qs],
            ).values_list("student_id", "status")
        )

        team_eval_map = {
            (evaluation.evaluator_id, evaluation.target_team_id): evaluation
            for evaluation in TeamEvaluation.objects.filter(
                evaluation_round=selected_round,
                evaluator__is_active=True,
            )
        }
        personal_eval_map = {
            (evaluation.evaluator_id, evaluation.target_student_id): evaluation
            for evaluation in PersonalEvaluation.objects.filter(
                evaluation_round=selected_round,
                evaluator__is_active=True,
            )
        }

        for membership in memberships_qs:
            evaluator = membership.student
            evaluator_name = evaluator.name
            evaluator_email = evaluator.user.email
            team = membership.team
            attendance_status = attendance_map.get(
                evaluator.id, RoundAttendance.Status.PRESENT
            )

            if attendance_status == RoundAttendance.Status.PRESENT:
                for target_team in active_teams:
                    if target_team.id == team.id:
                        continue
                    evaluation = team_eval_map.get((evaluator.id, target_team.id))
                    if evaluation and evaluation.is_submitted:
                        continue
                    state = "draft" if evaluation else "not_started"
                    summary["team_missing"] += 1
                    summary[
                        "draft_count" if state == "draft" else "not_started_count"
                    ] += 1
                    rows.append(
                        {
                            "type": "team",
                            "type_label": "팀 평가",
                            "evaluator_name": evaluator_name,
                            "evaluator_email": evaluator_email,
                            "evaluator_team": team.name,
                            "target_name": target_team.name,
                            "state": state,
                            "state_label": "임시저장" if state == "draft" else "미시작",
                            "attendance_label": "출석",
                        }
                    )
            else:
                summary["exempt_team_count"] += max(len(active_teams) - 1, 0)

            for target_membership in memberships_by_team.get(team.id, []):
                target = target_membership.student
                if target.id == evaluator.id:
                    continue
                evaluation = personal_eval_map.get((evaluator.id, target.id))
                if evaluation and evaluation.is_submitted:
                    continue
                state = "draft" if evaluation else "not_started"
                summary["personal_missing"] += 1
                summary[
                    "draft_count" if state == "draft" else "not_started_count"
                ] += 1
                rows.append(
                    {
                        "type": "personal",
                        "type_label": "개인 평가",
                        "evaluator_name": evaluator_name,
                        "evaluator_email": evaluator_email,
                        "evaluator_team": team.name,
                        "target_name": target.name,
                        "state": state,
                        "state_label": "임시저장" if state == "draft" else "미시작",
                        "attendance_label": dict(RoundAttendance.Status.choices).get(
                            attendance_status, "출석"
                        ),
                    }
                )

        complete_team_ids = complete_team_evaluator_ids(selected_round)
        complete_personal_ids = complete_personal_evaluator_ids(selected_round)

        membership_team_map = {m.student_id: m.team_id for m in memberships_qs}
        active_team_ids = {team.id for team in active_teams}
        team_member_ids = {}
        for membership in memberships_qs:
            team_member_ids.setdefault(membership.team_id, set()).add(
                membership.student_id
            )

        team_eligible_ids = {
            student_id
            for student_id, own_team_id in membership_team_map.items()
            if attendance_map.get(student_id, RoundAttendance.Status.PRESENT)
            == RoundAttendance.Status.PRESENT
            and len(active_team_ids - {own_team_id}) > 0
        }
        personal_eligible_ids = {
            student_id
            for student_id, own_team_id in membership_team_map.items()
            if len(team_member_ids.get(own_team_id, set()) - {student_id}) > 0
        }
        summary["team_incomplete_evaluators"] = len(
            team_eligible_ids - complete_team_ids
        )
        summary["personal_incomplete_evaluators"] = len(
            personal_eligible_ids - complete_personal_ids
        )

        partial_team_ids = {
            evaluator_id
            for evaluator_id in team_eligible_ids - complete_team_ids
            if any(
                key[0] == evaluator_id and evaluation.is_submitted
                for key, evaluation in team_eval_map.items()
            )
        }
        partial_personal_ids = {
            evaluator_id
            for evaluator_id in personal_eligible_ids - complete_personal_ids
            if any(
                key[0] == evaluator_id and evaluation.is_submitted
                for key, evaluation in personal_eval_map.items()
            )
        }
        summary["partial_excluded_evaluators"] = len(
            partial_team_ids | partial_personal_ids
        )

        if evaluation_type in {"team", "personal"}:
            rows = [row for row in rows if row["type"] == evaluation_type]

        if query:
            rows = [
                row
                for row in rows
                if query in row["evaluator_name"].lower()
                or query in (row["evaluator_email"] or "").lower()
                or query in row["evaluator_team"].lower()
                or query in row["target_name"].lower()
            ]

    summary["total_missing"] = summary["team_missing"] + summary["personal_missing"]
    return {"rows": rows, "summary": summary}
