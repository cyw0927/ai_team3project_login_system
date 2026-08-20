"""Supporting calculations used by result aggregation.

This module deliberately contains no HTTP/view concerns. It owns two result-side
post-processing rules that previously lived in ``views.common``:
- apply completed assignment scores to skill profiles
- calculate badge-only rankings
"""

from django.db.models import Avg

from ..models import (
    Assignment,
    AssignmentSkillImpact,
    HRTask,
    HRTaskEvaluation,
    StudentResult,
    StudentSkill,
)


def apply_assignment_skill_impacts(evaluation_round, result_rows):
    """Apply completed round assignment scores to student skill profiles.

    Recalculation is idempotent: previously applied impacts for the round are
    removed from the baseline before the new values are calculated.
    """
    if evaluation_round.status != evaluation_round.Status.ENDED:
        return

    assignments = list(
        Assignment.objects.filter(evaluation_round=evaluation_round)
        .prefetch_related("required_skills__skill")
        .order_by("id")
    )
    requirements = {
        assignment.id: list(assignment.required_skills.all())
        for assignment in assignments
    }
    if not any(requirements.values()):
        return

    assignment_ids = [assignment.id for assignment in assignments]
    for result in result_rows:
        old_impacts = list(
            AssignmentSkillImpact.objects.filter(
                assignment_id__in=assignment_ids,
                student=result.student,
            )
        )
        old_by_skill = {}
        for impact in old_impacts:
            old_by_skill.setdefault(impact.skill_id, 0)
            old_by_skill[impact.skill_id] += impact.applied_delta

        skill_ids = {
            requirement.skill_id
            for assignment in assignments
            for requirement in requirements[assignment.id]
        }

        for skill_id in skill_ids:
            profile, _ = StudentSkill.objects.get_or_create(
                student=result.student,
                skill_id=skill_id,
                defaults={"score": 0, "note": "기본 과제 평가로 자동 생성"},
            )
            baseline = max(0, min(100, profile.score - old_by_skill.get(skill_id, 0)))
            running = baseline

            for assignment in assignments:
                requirement = next(
                    (
                        item
                        for item in requirements[assignment.id]
                        if item.skill_id == skill_id
                    ),
                    None,
                )
                if not requirement:
                    continue

                raw_score = (
                    float(result.team_score)
                    if assignment.assignment_type == Assignment.AssignmentType.TEAM
                    else float(result.personal_score)
                )
                performance = max(0.0, min(100.0, raw_score * 20.0))
                delta = round(
                    (performance - running)
                    * (requirement.weight / 100)
                    * 0.30
                )
                next_score = max(0, min(100, running + delta))
                actual_delta = next_score - running

                AssignmentSkillImpact.objects.update_or_create(
                    assignment=assignment,
                    student=result.student,
                    skill_id=skill_id,
                    defaults={
                        "performance_score": performance,
                        "skill_weight": requirement.weight,
                        "previous_score": running,
                        "new_score": next_score,
                        "applied_delta": actual_delta,
                    },
                )
                running = next_score

            if profile.score != running:
                profile.score = running
                profile.save(update_fields=["score", "updated_at"])


def badge_rank_map(evaluation_round, result_rows=None):
    """Return badge-only ranks without mutating official StudentResult ranks.

    If a completed HR task score exists, badge score uses evaluation 80% and HR
    task average 20%. Otherwise the official evaluation score is used as-is.
    """
    if not evaluation_round:
        return {}

    if result_rows is None:
        result_rows = list(
            StudentResult.objects.filter(
                evaluation_round=evaluation_round,
                is_excluded=False,
            ).select_related("student")
        )

    hr_rows = (
        HRTaskEvaluation.objects.filter(
            task__evaluation_round=evaluation_round,
            task__status=HRTask.Status.COMPLETED,
        )
        .values("student_id")
        .annotate(avg_score=Avg("score"))
    )
    hr_avg_map = {
        row["student_id"]: float(row["avg_score"])
        for row in hr_rows
    }

    ranked = []
    for result in result_rows:
        evaluation_score = float(result.final_score)
        hr_score = hr_avg_map.get(result.student_id)
        badge_score = (
            evaluation_score
            if hr_score is None
            else evaluation_score * 0.80 + hr_score * 0.20
        )
        ranked.append((result.student_id, badge_score, evaluation_score))

    ranked.sort(key=lambda row: (row[1], row[2]), reverse=True)

    rank_map = {}
    previous_key = None
    current_rank = 0
    for index, (student_id, badge_score, evaluation_score) in enumerate(ranked, start=1):
        key = (round(badge_score, 8), round(evaluation_score, 8))
        if key != previous_key:
            current_rank = index
            previous_key = key
        rank_map[student_id] = current_rank

    return rank_map
