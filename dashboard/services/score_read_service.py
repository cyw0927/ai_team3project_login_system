"""Read models for admin score and ranking pages."""

from django.db.models import Count

from ..models import (
    PersonalEvaluation,
    StudentResult,
    Team,
    TeamEvaluation,
    TeamMembership,
    TeamResult,
)


def build_team_score_rows(evaluation_round):
    if not evaluation_round:
        return []

    # TeamResult represents peer/student team evaluation only. Staff tutor reviews
    # are a separate score component and must not inflate the peer submission count.
    counts = dict(
        TeamEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            is_submitted=True,
            evaluator__user__is_staff=False,
        )
        .values("target_team_id")
        .annotate(c=Count("id"))
        .values_list("target_team_id", "c")
    )
    results = {
        result.team_id: result
        for result in TeamResult.objects.filter(evaluation_round=evaluation_round)
    }

    rows = []
    for team in Team.objects.filter(
        evaluation_round=evaluation_round,
        is_active=True,
    ).order_by("name"):
        result = results.get(team.id)
        rows.append({
            "name": team.name,
            "evaluation_count": counts.get(team.id, 0),
            "score": result.score if result else None,
            "rank": result.rank if result and not result.is_excluded else None,
            "is_excluded": result.is_excluded if result else False,
        })
    return rows


def build_personal_score_rows(evaluation_round):
    if not evaluation_round:
        return []

    counts = dict(
        PersonalEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            is_submitted=True,
        )
        .values("target_student_id")
        .annotate(c=Count("id"))
        .values_list("target_student_id", "c")
    )

    rows = []
    results = (
        StudentResult.objects.filter(evaluation_round=evaluation_round)
        .select_related("student__user")
        .order_by("student__user__first_name", "student__user__username")
    )
    for result in results:
        rows.append({
            "student_name": result.student.name,
            "evaluation_count": counts.get(result.student_id, 0),
            "score": result.personal_score,
            "team_score": result.team_score,
            "final_score": result.final_score,
            "is_excluded": result.is_excluded,
        })
    return rows


def build_ranking_rows(evaluation_round):
    if not evaluation_round:
        return []

    memberships = {
        membership.student_id: membership.team
        for membership in TeamMembership.objects.filter(
            team__evaluation_round=evaluation_round,
        ).select_related("team")
    }
    results = (
        StudentResult.objects.filter(evaluation_round=evaluation_round)
        .select_related("student__user")
        .order_by(
            "is_excluded",
            "rank",
            "student__user__first_name",
            "student__user__username",
        )
    )

    rows = []
    for result in results:
        team = memberships.get(result.student_id)
        rows.append({
            "rank": result.rank if not result.is_excluded else "제외",
            "student_name": result.student.name,
            "team_name": team.name if team else "-",
            "team_score": result.team_score,
            "personal_score": result.personal_score,
            "final_score": result.final_score,
            "is_excluded": result.is_excluded,
        })
    return rows
