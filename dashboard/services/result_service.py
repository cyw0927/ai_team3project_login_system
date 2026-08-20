"""Result calculation service.

The public view modules call this service so score aggregation and ranking
are no longer owned by the HTTP view layer. Helper calculations remain in
``views.common`` for this first refactor step and will be migrated separately.
"""

from django.db.models import Avg

from ..models import (
    EvaluationRound, PersonalEvaluation, PersonalEvaluationScore, Student,
    StudentBadge, StudentResult, Team, TeamEvaluation, TeamEvaluationScore,
    TeamMembership, TeamResult,
)
from ..views.common import (
    _apply_assignment_skill_impacts,
    _badge_rank_map,
    _complete_personal_evaluator_ids,
    _complete_team_evaluator_ids,
)


def _recalculate_round_results(evaluation_round, tutor_weight=None):
    """평가 결과를 회차 가중치에 따라 다시 계산한다.

    핵심 규칙:
    - 학생 평가자가 본인의 필수 평가 대상을 전부 최종 제출해야 그 평가자의 데이터 전체를 반영한다.
    - 일부만 제출한 학생 평가자는 제출한 대상까지 포함해 해당 회차 점수 집계에서 전부 제외한다.
    - 팀 점수는 학생들의 타팀 평가, 개인 점수는 같은 팀 동료 평가를 사용한다.
    - 튜터 평가는 staff 계정이 팀 단위로 제출한 평가를 사용한다.
    - 튜터 가중치는 100 - 팀 가중치 - 개인 가중치로 계산한다.
      예: 팀40 + 개인30이면 튜터30. 기존 팀40 + 개인60 회차는 튜터0으로 그대로 유지된다.
    - 튜터 가중치가 0보다 큰 회차에서 해당 팀의 튜터 평가가 아직 없으면 그 팀 학생은 최종 순위에서 제외한다.

    최종 점수 = 팀점수 × 팀가중치 + 개인점수 × 개인가중치 + 튜터팀점수 × 튜터가중치 + 관리자 보정점수
    """
    TeamResult.objects.filter(evaluation_round=evaluation_round).update(is_excluded=True, rank=None)
    StudentResult.objects.filter(evaluation_round=evaluation_round).update(is_excluded=True, rank=None)

    complete_team_evaluator_ids = _complete_team_evaluator_ids(evaluation_round)
    complete_personal_evaluator_ids = _complete_personal_evaluator_ids(evaluation_round)

    team_weight_percent = int(evaluation_round.team_weight or 0)
    personal_weight_percent = int(evaluation_round.personal_weight or 0)
    if tutor_weight is None:
        tutor_weight_percent = max(0, 100 - team_weight_percent - personal_weight_percent)
    else:
        tutor_weight_percent = max(0, int(tutor_weight))

    total_weight = team_weight_percent + personal_weight_percent + tutor_weight_percent
    if total_weight <= 0:
        team_weight = personal_weight = tutor_weight_ratio = 0.0
    else:
        team_weight = team_weight_percent / total_weight
        personal_weight = personal_weight_percent / total_weight
        tutor_weight_ratio = tutor_weight_percent / total_weight

    teams = Team.objects.filter(evaluation_round=evaluation_round, is_active=True)
    team_score_map = {}
    tutor_score_map = {}
    tutor_submission_count_map = {}

    for team in teams:
        team_score_qs = TeamEvaluationScore.objects.filter(
            evaluation__evaluation_round=evaluation_round,
            evaluation__target_team=team,
            evaluation__evaluator_id__in=complete_team_evaluator_ids,
            evaluation__is_submitted=True,
        )
        team_avg = team_score_qs.aggregate(avg=Avg("score"))["avg"] or 0
        valid_team_evaluations = TeamEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            target_team=team,
            evaluator_id__in=complete_team_evaluator_ids,
            is_submitted=True,
        ).count()
        team_excluded = valid_team_evaluations == 0
        team_score_map[team.id] = float(team_avg)
        TeamResult.objects.update_or_create(
            evaluation_round=evaluation_round,
            team=team,
            defaults={"score": team_avg, "is_excluded": team_excluded},
        )

        tutor_score_qs = TeamEvaluationScore.objects.filter(
            evaluation__evaluation_round=evaluation_round,
            evaluation__target_team=team,
            evaluation__evaluator__user__is_staff=True,
            evaluation__is_submitted=True,
        )
        tutor_avg = tutor_score_qs.aggregate(avg=Avg("score"))["avg"] or 0
        tutor_submissions = TeamEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            target_team=team,
            evaluator__user__is_staff=True,
            is_submitted=True,
        ).count()
        tutor_score_map[team.id] = float(tutor_avg)
        tutor_submission_count_map[team.id] = tutor_submissions

    memberships = (
        TeamMembership.objects.filter(team__evaluation_round=evaluation_round)
        .select_related("student", "team")
    )
    student_team_map = {m.student_id: m.team for m in memberships}

    students = Student.objects.filter(
        id__in=student_team_map.keys(), is_active=True, user__is_active=True
    ).select_related("user")

    result_rows = []
    for student in students:
        personal_score_qs = PersonalEvaluationScore.objects.filter(
            evaluation__evaluation_round=evaluation_round,
            evaluation__target_student=student,
            evaluation__evaluator_id__in=complete_personal_evaluator_ids,
            evaluation__is_submitted=True,
        )
        personal_avg = personal_score_qs.aggregate(avg=Avg("score"))["avg"] or 0
        valid_personal_evaluations = PersonalEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            target_student=student,
            evaluator_id__in=complete_personal_evaluator_ids,
            is_submitted=True,
        ).count()
        team = student_team_map.get(student.id)
        team_avg = team_score_map.get(team.id, 0) if team else 0
        tutor_avg = tutor_score_map.get(team.id, 0) if team else 0
        team_result = TeamResult.objects.filter(evaluation_round=evaluation_round, team=team).first() if team else None
        tutor_required_missing = bool(
            tutor_weight_percent > 0
            and team
            and tutor_submission_count_map.get(team.id, 0) == 0
        )
        excluded = (
            valid_personal_evaluations == 0
            or not team_result
            or team_result.is_excluded
            or tutor_required_missing
        )
        base_score = (
            float(personal_avg) * personal_weight
            + float(team_avg) * team_weight
            + float(tutor_avg) * tutor_weight_ratio
        )
        existing_result = StudentResult.objects.filter(evaluation_round=evaluation_round, student=student).first()
        adjustment_score = float(existing_result.adjustment_score) if existing_result else 0
        final_score = base_score + adjustment_score
        result, _ = StudentResult.objects.update_or_create(
            evaluation_round=evaluation_round,
            student=student,
            defaults={
                "team_score": team_avg,
                "personal_score": personal_avg,
                "base_score": base_score,
                "final_score": final_score,
                "is_excluded": excluded,
            },
        )
        if not excluded:
            result_rows.append(result)

    # 공동 점수는 같은 등수, 다음 등수는 건너뛰는 competition ranking.
    ordered = sorted(
        result_rows,
        key=lambda r: (float(r.final_score), float(r.personal_score)),
        reverse=True,
    )
    previous_key = None
    current_rank = 0
    for index, result in enumerate(ordered, start=1):
        key = (result.final_score, result.personal_score)
        if key != previous_key:
            current_rank = index
            previous_key = key
        if result.rank != current_rank:
            result.rank = current_rank
            result.save(update_fields=["rank", "updated_at"])

    # 종료된 기본 과제의 결과를 역량 프로필에 반영한다.
    _apply_assignment_skill_impacts(evaluation_round, ordered)

    # 배지 산정은 공식 최종점수와 분리한다.
    # 역량 과제가 회차에 연결되어 평가 완료된 경우:
    #   배지점수 = 기존 평가 최종점수 80% + 역량 과제 평균점수 20%
    # 연결된 과제 평가가 없는 수강생은 기존 평가 최종점수를 그대로 사용한다.
    current_badge_ranks = _badge_rank_map(evaluation_round, ordered)

    # MVP: 배지 전용 순위 1위. 동점은 공동 수상.
    mvp_student_ids = [
        student_id
        for student_id, rank in current_badge_ranks.items()
        if rank == 1
    ]
    StudentBadge.objects.filter(
        evaluation_round=evaluation_round,
        badge_type=StudentBadge.BadgeType.MVP,
    ).exclude(student_id__in=mvp_student_ids).delete()
    for student_id in mvp_student_ids:
        StudentBadge.objects.get_or_create(
            evaluation_round=evaluation_round,
            student_id=student_id,
            badge_type=StudentBadge.BadgeType.MVP,
        )

    previous_round = (
        EvaluationRound.objects.filter(
            start_at__lt=evaluation_round.start_at,
            status=EvaluationRound.Status.ENDED,
        )
        .order_by("-start_at")
        .first()
    )
    previous_badge_ranks = _badge_rank_map(previous_round) if previous_round else {}

    # 성장왕: 직전 회차 대비 배지 전용 순위가 가장 많이 상승한 학생.
    growth_student_ids = []
    improvements = []
    for student_id, current_rank in current_badge_ranks.items():
        previous_rank = previous_badge_ranks.get(student_id)
        if previous_rank:
            improvement = previous_rank - current_rank
            if improvement > 0:
                improvements.append((student_id, improvement))

    if improvements:
        best_improvement = max(improvement for _, improvement in improvements)
        growth_student_ids = [
            student_id
            for student_id, improvement in improvements
            if improvement == best_improvement
        ]

    StudentBadge.objects.filter(
        evaluation_round=evaluation_round,
        badge_type=StudentBadge.BadgeType.GROWTH,
    ).exclude(student_id__in=growth_student_ids).delete()
    for student_id in growth_student_ids:
        StudentBadge.objects.get_or_create(
            evaluation_round=evaluation_round,
            student_id=student_id,
            badge_type=StudentBadge.BadgeType.GROWTH,
        )

    # 연속 우수: 직전/현재 회차의 배지 전용 순위가 모두 Top 3.
    current_top3_ids = {
        student_id
        for student_id, rank in current_badge_ranks.items()
        if rank <= 3
    }
    previous_top3_ids = {
        student_id
        for student_id, rank in previous_badge_ranks.items()
        if rank <= 3
    }
    consistent_student_ids = sorted(current_top3_ids & previous_top3_ids)

    StudentBadge.objects.filter(
        evaluation_round=evaluation_round,
        badge_type=StudentBadge.BadgeType.CONSISTENT,
    ).exclude(student_id__in=consistent_student_ids).delete()
    for student_id in consistent_student_ids:
        StudentBadge.objects.get_or_create(
            evaluation_round=evaluation_round,
            student_id=student_id,
            badge_type=StudentBadge.BadgeType.CONSISTENT,
        )

    team_results = list(TeamResult.objects.filter(evaluation_round=evaluation_round, is_excluded=False))
    team_results.sort(key=lambda r: float(r.score), reverse=True)
    previous_score = None
    current_rank = 0
    for index, result in enumerate(team_results, start=1):
        if result.score != previous_score:
            current_rank = index
            previous_score = result.score
        if result.rank != current_rank:
            result.rank = current_rank
            result.save(update_fields=["rank", "updated_at"])
