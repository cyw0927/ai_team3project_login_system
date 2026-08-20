"""Tutor team-evaluation business logic.

HTTP views validate request routing and messages; this module owns tutor profile
resolution, evaluation state preparation and score persistence.
"""

from dataclasses import dataclass

from django.db.models import Avg
from django.utils import timezone

from ..models import (
    EvaluationTemplate,
    Student,
    Team,
    TeamEvaluation,
    TeamEvaluationScore,
)
from .scoring_policy import tutor_weight_for


@dataclass
class TutorEvaluationState:
    teams: list
    criteria: list
    rows: list
    completed_count: int
    can_edit: bool
    tutor_weight: int


def get_tutor_profile(user):
    """Return the temporary Student-backed tutor profile used by current schema."""
    profile, _ = Student.objects.get_or_create(
        user=user,
        defaults={"is_active": False, "affiliation": "튜터"},
    )
    return profile


def build_tutor_evaluation_state(evaluation_round, user):
    """Build tutor evaluation rows for one round without HTTP concerns."""
    tutor_weight = tutor_weight_for(evaluation_round)
    teams = list(
        Team.objects.filter(evaluation_round=evaluation_round, is_active=True).order_by("name")
    )
    template = (
        EvaluationTemplate.objects.filter(
            evaluation_round=evaluation_round,
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
            is_active=True,
        )
        .prefetch_related("criteria")
        .first()
    )
    criteria = list(template.criteria.all().order_by("order", "id")) if template else []
    can_edit = bool(
        evaluation_round.status == evaluation_round.Status.IN_PROGRESS
        and evaluation_round.evaluation_started
        and not evaluation_round.is_locked
    )

    tutor = get_tutor_profile(user)
    own_evaluations = {
        evaluation.target_team_id: evaluation
        for evaluation in TeamEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            evaluator=tutor,
        ).prefetch_related("scores")
    }
    completed_count = sum(
        1 for evaluation in own_evaluations.values() if evaluation.is_submitted
    )

    all_tutor_averages = dict(
        TeamEvaluationScore.objects.filter(
            evaluation__evaluation_round=evaluation_round,
            evaluation__is_submitted=True,
            evaluation__evaluator__user__is_staff=True,
        )
        .values("evaluation__target_team_id")
        .annotate(avg=Avg("score"))
        .values_list("evaluation__target_team_id", "avg")
    )

    rows = []
    for team in teams:
        evaluation = own_evaluations.get(team.id)
        score_map = (
            {item.criterion_id: item.score for item in evaluation.scores.all()}
            if evaluation
            else {}
        )
        rows.append({
            "team": team,
            "evaluation": evaluation,
            "criterion_rows": [
                {
                    "criterion": criterion,
                    "value": score_map.get(criterion.id),
                    "options": range(1, criterion.max_score + 1),
                }
                for criterion in criteria
            ],
            "team_tutor_average": all_tutor_averages.get(team.id),
        })

    return TutorEvaluationState(
        teams=teams,
        criteria=criteria,
        rows=rows,
        completed_count=completed_count,
        can_edit=can_edit,
        tutor_weight=tutor_weight,
    )


def save_tutor_team_evaluation(evaluation_round, user, team_id, post_data):
    """Persist one tutor's team evaluation and return the target team.

    Raises ValueError for policy/input errors so the view can choose presentation.
    """
    state = build_tutor_evaluation_state(evaluation_round, user)
    if not state.can_edit:
        raise ValueError("평가가 진행 중이고 잠금 해제된 상태에서만 튜터 평가를 저장할 수 있습니다.")
    if not state.criteria:
        raise ValueError("이 회차에 적용된 팀 평가 문항이 없습니다.")

    try:
        target_team_id = int(team_id)
    except (TypeError, ValueError):
        raise ValueError("평가할 팀 정보가 올바르지 않습니다.")

    team = next((item for item in state.teams if item.id == target_team_id), None)
    if team is None:
        raise ValueError("평가할 활성 팀을 찾을 수 없습니다.")

    score_values = {}
    for criterion in state.criteria:
        raw = (post_data.get(f"score_{criterion.id}") or "").strip()
        try:
            score = int(raw)
        except (TypeError, ValueError):
            score = 0
        if score < 1 or score > criterion.max_score:
            raise ValueError(
                f"{criterion.title}: 1~{criterion.max_score}점 사이로 입력해 주세요."
            )
        score_values[criterion.id] = score

    tutor = get_tutor_profile(user)
    evaluation, _ = TeamEvaluation.objects.get_or_create(
        evaluation_round=evaluation_round,
        evaluator=tutor,
        target_team=team,
    )
    evaluation.comment = (post_data.get("comment") or "").strip()
    evaluation.is_submitted = True
    evaluation.submitted_at = timezone.now()
    evaluation.save(
        update_fields=["comment", "is_submitted", "submitted_at", "updated_at"]
    )

    for criterion in state.criteria:
        TeamEvaluationScore.objects.update_or_create(
            evaluation=evaluation,
            criterion=criterion,
            defaults={"score": score_values[criterion.id]},
        )

    return team
