"""Evaluator completion rules used by score aggregation.

This module owns the policy that only students who finished every required
team/personal evaluation contribute scores to the official result.
"""

from ..models import (
    PersonalEvaluation,
    RoundAttendance,
    Team,
    TeamEvaluation,
    TeamMembership,
)


def complete_team_evaluator_ids(evaluation_round):
    """Return students who completed every required other-team evaluation."""
    active_team_ids = list(
        Team.objects.filter(
            evaluation_round=evaluation_round,
            is_active=True,
        ).values_list("id", flat=True)
    )
    if not active_team_ids:
        return set()

    memberships = {
        membership.student_id: membership.team_id
        for membership in TeamMembership.objects.filter(
            team__evaluation_round=evaluation_round,
            student__is_active=True,
            student__user__is_active=True,
        ).select_related("student__user")
    }
    if not memberships:
        return set()

    exempt_student_ids = set(
        RoundAttendance.objects.filter(
            evaluation_round=evaluation_round,
            student_id__in=memberships.keys(),
            status__in={
                RoundAttendance.Status.ABSENT,
                RoundAttendance.Status.EXCUSED,
            },
        ).values_list("student_id", flat=True)
    )

    submitted_map = {}
    for evaluator_id, target_team_id in TeamEvaluation.objects.filter(
        evaluation_round=evaluation_round,
        evaluator_id__in=memberships.keys(),
        target_team_id__in=active_team_ids,
        is_submitted=True,
    ).values_list("evaluator_id", "target_team_id"):
        submitted_map.setdefault(evaluator_id, set()).add(target_team_id)

    complete_ids = set()
    active_team_set = set(active_team_ids)
    for evaluator_id, own_team_id in memberships.items():
        if evaluator_id in exempt_student_ids:
            continue
        required_targets = active_team_set - {own_team_id}
        if not required_targets:
            continue
        submitted_targets = submitted_map.get(evaluator_id, set()) & required_targets
        if submitted_targets >= required_targets:
            complete_ids.add(evaluator_id)

    return complete_ids


def complete_personal_evaluator_ids(evaluation_round):
    """Return students who completed every required same-team peer evaluation."""
    memberships = list(
        TeamMembership.objects.filter(
            team__evaluation_round=evaluation_round,
            student__is_active=True,
            student__user__is_active=True,
        ).values_list("student_id", "team_id")
    )
    if not memberships:
        return set()

    team_members = {}
    student_team = {}
    for student_id, team_id in memberships:
        student_team[student_id] = team_id
        team_members.setdefault(team_id, set()).add(student_id)

    submitted_map = {}
    for evaluator_id, target_student_id in PersonalEvaluation.objects.filter(
        evaluation_round=evaluation_round,
        evaluator_id__in=student_team.keys(),
        is_submitted=True,
    ).values_list("evaluator_id", "target_student_id"):
        submitted_map.setdefault(evaluator_id, set()).add(target_student_id)

    complete_ids = set()
    for evaluator_id, team_id in student_team.items():
        required_targets = team_members.get(team_id, set()) - {evaluator_id}
        if not required_targets:
            continue
        submitted_targets = submitted_map.get(evaluator_id, set()) & required_targets
        if submitted_targets >= required_targets:
            complete_ids.add(evaluator_id)

    return complete_ids
