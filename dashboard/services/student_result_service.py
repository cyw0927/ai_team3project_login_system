"""Student result presentation data builder.

Keeps result visibility, comparison, chart, history and feedback assembly out of
the HTTP view so the view only resolves the request and renders a template.
"""

from django.db.models import Avg
from django.utils import timezone

from dashboard.models import (
    AdminStudentComment,
    EvaluationTemplate,
    PersonalEvaluation,
    ResultPublishSetting,
    StudentResult,
    TeamMembership,
    TeamResult,
)


def _available_rounds(settings, selected_round_id):
    return [
        {
            "id": setting.evaluation_round_id,
            "name": setting.evaluation_round.name,
            "selected": setting.evaluation_round_id == selected_round_id,
        }
        for setting in settings
    ]


def _comparison_item(label, score, average):
    delta = score - average if average is not None else None
    return {
        "label": label,
        "score": score,
        "average": average,
        "delta": delta,
        "compare_label": (
            "평균보다 높음" if delta is not None and delta > 0
            else "평균보다 낮음" if delta is not None and delta < 0
            else "평균과 동일"
        ) if delta is not None else "-",
    }


def _build_comparison(evaluation_round, student_result):
    peer_results = StudentResult.objects.filter(
        evaluation_round=evaluation_round,
        is_excluded=False,
    )
    averages = peer_results.aggregate(
        team_avg=Avg("team_score"),
        personal_avg=Avg("personal_score"),
        final_avg=Avg("final_score"),
    )
    breakdown = [
        _comparison_item(
            f"팀 평가 점수 ({evaluation_round.team_weight}%)",
            student_result.team_score,
            averages["team_avg"],
        ),
        _comparison_item(
            f"개인 평가 점수 ({evaluation_round.personal_weight}%)",
            student_result.personal_score,
            averages["personal_avg"],
        ),
        _comparison_item(
            "최종 점수",
            student_result.final_score,
            averages["final_avg"],
        ),
    ]
    comparison_summary = {
        "participant_count": peer_results.count(),
        "final_average": averages["final_avg"],
        "final_delta": (
            student_result.final_score - averages["final_avg"]
            if averages["final_avg"] is not None else None
        ),
    }
    return breakdown, comparison_summary


def _build_radar_chart(student, evaluation_round):
    memberships = TeamMembership.objects.filter(
        team__evaluation_round=evaluation_round
    ).values_list("student_id", "team_id")
    student_team_map = {student_id: team_id for student_id, team_id in memberships}

    personal_evaluations = (
        PersonalEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            is_submitted=True,
        )
        .prefetch_related("scores__criterion__template")
    )

    mine = {}
    cohort = {}
    criterion_meta = {}
    for evaluation in personal_evaluations:
        evaluator_team = student_team_map.get(evaluation.evaluator_id)
        target_team = student_team_map.get(evaluation.target_student_id)
        if (
            not evaluator_team
            or evaluator_team != target_team
            or evaluation.evaluator_id == evaluation.target_student_id
        ):
            continue

        for score_row in evaluation.scores.all():
            criterion = score_row.criterion
            if criterion.template.evaluation_type != EvaluationTemplate.EvaluationType.PERSONAL:
                continue
            key = criterion.id
            criterion_meta[key] = {
                "label": criterion.title,
                "max_score": criterion.max_score or 5,
                "order": criterion.order,
            }
            cohort.setdefault(key, []).append(float(score_row.score))
            if evaluation.target_student_id == student.id:
                mine.setdefault(key, []).append(float(score_row.score))

    radar_items = []
    for criterion_id, meta in sorted(
        criterion_meta.items(), key=lambda item: (item[1]["order"], item[0])
    ):
        mine_scores = mine.get(criterion_id, [])
        if not mine_scores:
            continue
        my_avg = sum(mine_scores) / len(mine_scores)
        cohort_scores = cohort.get(criterion_id, [])
        cohort_avg = sum(cohort_scores) / len(cohort_scores) if cohort_scores else 0
        max_score = float(meta["max_score"])
        radar_items.append({
            "label": meta["label"],
            "score": round(my_avg, 2),
            "average": round(cohort_avg, 2),
            "max_score": max_score,
            "score_percent": round((my_avg / max_score) * 100, 2) if max_score else 0,
            "average_percent": round((cohort_avg / max_score) * 100, 2) if max_score else 0,
        })

    return {"items": radar_items} if len(radar_items) >= 3 else None


def _build_score_history(student, selected_round_id, now):
    score_history = []
    history_settings = (
        ResultPublishSetting.objects.filter(
            evaluation_round__student_results__student=student,
            show_personal_score=True,
        )
        .select_related("evaluation_round")
        .distinct()
        .order_by("evaluation_round__start_at")
    )
    for history_setting in history_settings:
        if not (
            history_setting.is_published
            or (history_setting.publish_at and history_setting.publish_at <= now)
        ):
            continue
        history_result = StudentResult.objects.filter(
            evaluation_round=history_setting.evaluation_round,
            student=student,
            is_excluded=False,
        ).first()
        if not history_result or history_result.final_score is None:
            continue
        score_history.append({
            "round_id": history_setting.evaluation_round_id,
            "round_name": history_setting.evaluation_round.name,
            "start_at": history_setting.evaluation_round.start_at,
            "team_score": history_result.team_score,
            "personal_score": history_result.personal_score,
            "final_score": history_result.final_score,
            "rank": history_result.rank if history_setting.show_overall_rank else None,
            "is_selected": history_setting.evaluation_round_id == selected_round_id,
        })
    return score_history


def build_student_result_context(student, selected_round_id="", now=None):
    """Build the template context payload for the student's published result page."""
    now = now or timezone.now()
    settings_qs = list(
        ResultPublishSetting.objects.filter(
            evaluation_round__student_results__student=student
        )
        .select_related("evaluation_round")
        .distinct()
        .order_by("-evaluation_round__start_at")
    )
    visible_settings = [
        setting for setting in settings_qs
        if setting.is_published or (setting.publish_at and setting.publish_at <= now)
    ]

    selected_round_id = (selected_round_id or "").strip()
    publish_setting = None
    if selected_round_id.isdigit():
        publish_setting = next(
            (
                setting for setting in visible_settings
                if setting.evaluation_round_id == int(selected_round_id)
            ),
            None,
        )
    if publish_setting is None and visible_settings:
        publish_setting = visible_settings[0]

    if not publish_setting:
        return {
            "result_published": False,
            "result": {},
            "available_result_rounds": [],
        }

    evaluation_round = publish_setting.evaluation_round
    student_result = StudentResult.objects.filter(
        evaluation_round=evaluation_round,
        student=student,
        is_excluded=False,
    ).first()
    available_rounds = _available_rounds(visible_settings, evaluation_round.id)
    if not student_result:
        return {
            "result_published": False,
            "result": {},
            "available_result_rounds": available_rounds,
        }

    membership = (
        TeamMembership.objects.filter(
            team__evaluation_round=evaluation_round,
            student=student,
        )
        .select_related("team")
        .first()
    )
    team = membership.team if membership else None
    team_result = (
        TeamResult.objects.filter(
            evaluation_round=evaluation_round,
            team=team,
            is_excluded=False,
        ).first()
        if team else None
    )

    breakdown = []
    comparison_summary = None
    radar_chart = None
    score_history = []
    if publish_setting.show_personal_score:
        breakdown, comparison_summary = _build_comparison(
            evaluation_round, student_result
        )
        radar_chart = _build_radar_chart(student, evaluation_round)
        score_history = _build_score_history(student, evaluation_round.id, now)

    comments = []
    admin_feedback = None
    if publish_setting.show_comments:
        comments = list(
            PersonalEvaluation.objects.filter(
                evaluation_round=evaluation_round,
                target_student=student,
                is_submitted=True,
            )
            .exclude(comment="")
            .values_list("comment", flat=True)
        )
        admin_feedback = (
            AdminStudentComment.objects.filter(
                evaluation_round=evaluation_round,
                student=student,
            )
            .select_related("created_by")
            .first()
        )

    team_rankings = []
    if publish_setting.show_all_team_ranks:
        team_rankings = list(
            TeamResult.objects.filter(
                evaluation_round=evaluation_round,
                is_excluded=False,
            )
            .select_related("team")
            .order_by("rank", "team__name")
        )

    first_team = None
    if publish_setting.show_team_first_place:
        first_team = (
            TeamResult.objects.filter(
                evaluation_round=evaluation_round,
                rank=1,
                is_excluded=False,
            )
            .select_related("team")
            .first()
        )

    result = {
        "round_id": evaluation_round.id,
        "round_name": evaluation_round.name,
        "team_name": team.name if team else "-",
        "team_rank": team_result.rank if (team_result and publish_setting.show_all_team_ranks) else None,
        "team_score": student_result.team_score if publish_setting.show_personal_score else None,
        "personal_score": student_result.personal_score if publish_setting.show_personal_score else None,
        "final_score": student_result.final_score if publish_setting.show_personal_score else None,
        "overall_rank": student_result.rank if publish_setting.show_overall_rank else None,
        "breakdown": breakdown,
        "comparison_summary": comparison_summary,
        "radar_chart": radar_chart,
        "score_history": score_history if publish_setting.show_personal_score else [],
        "comments": comments,
        "admin_feedback": admin_feedback,
        "team_rankings": team_rankings,
        "first_team": first_team,
        "show_personal_score": publish_setting.show_personal_score,
        "show_overall_rank": publish_setting.show_overall_rank,
    }
    return {
        "result_published": True,
        "result": result,
        "available_result_rounds": available_rounds,
    }
