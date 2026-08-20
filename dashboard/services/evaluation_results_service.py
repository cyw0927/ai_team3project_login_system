from django.db import connection
from django.db.models import Avg, Count, Q
from django.utils import timezone

from dashboard.models import (
    EvaluationRound,
    PersonalEvaluation,
    ResultPublishSetting,
    RoundAttendance,
    StudentResult,
    Team,
    TeamEvaluation,
    TeamMembership,
    TeamResult,
)

RAW_TABLE = "dashboard_officialevaluationresponse"


def _selected_round(request, rounds):
    round_id = request.GET.get("round") or request.POST.get("round_id")
    if round_id:
        return rounds.filter(pk=round_id).first()
    return rounds.first()


def _official_raw_progress(evaluation_round):
    """Return source-row progress for imported AX2 rounds.

    Imported data is a completed historical dataset. Its source rows are the
    authoritative submission count; canonical evaluator-target rows can be fewer
    because duplicate source responses are intentionally collapsed for tables with
    unique constraints.
    """
    if RAW_TABLE not in connection.introspection.table_names():
        return None

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT response_type, COUNT(*)
            FROM {RAW_TABLE}
            WHERE evaluation_round_id = %s
            GROUP BY response_type
            """,
            [evaluation_round.id],
        )
        counts = {response_type: count for response_type, count in cursor.fetchall()}

    team_count = counts.get("team", 0)
    personal_count = counts.get("personal", 0)
    if not team_count and not personal_count:
        return None

    return {
        "team_required": team_count,
        "team_completed": team_count,
        "personal_required": personal_count,
        "personal_completed": personal_count,
    }


def _submission_progress(evaluation_round, memberships_qs, active_teams, attendance_map):
    memberships = list(memberships_qs)
    members_by_team = {}
    for membership in memberships:
        members_by_team.setdefault(membership.team_id, []).append(membership.student_id)

    submitted_team_pairs = set(
        TeamEvaluation.objects.filter(evaluation_round=evaluation_round, is_submitted=True)
        .values_list("evaluator_id", "target_team_id")
    )
    submitted_personal_pairs = set(
        PersonalEvaluation.objects.filter(evaluation_round=evaluation_round, is_submitted=True)
        .values_list("evaluator_id", "target_student_id")
    )

    team_required = team_completed = 0
    personal_required = personal_completed = 0

    for membership in memberships:
        evaluator_id = membership.student_id
        team_id = membership.team_id
        attendance_status = attendance_map.get(evaluator_id, RoundAttendance.Status.PRESENT)

        if attendance_status == RoundAttendance.Status.PRESENT:
            for target_team in active_teams:
                if target_team.id == team_id:
                    continue
                team_required += 1
                team_completed += (evaluator_id, target_team.id) in submitted_team_pairs

        for target_student_id in members_by_team.get(team_id, []):
            if target_student_id == evaluator_id:
                continue
            personal_required += 1
            personal_completed += (evaluator_id, target_student_id) in submitted_personal_pairs

    return {
        "team_required": team_required,
        "team_completed": team_completed,
        "personal_required": personal_required,
        "personal_completed": personal_completed,
    }


def _evaluation_review_flags(evaluation_round):
    flags = []

    def add_flag(kind, evaluator, target, scores):
        if len(scores) < 2:
            return
        avg = sum(scores) / len(scores)
        unique = set(scores)
        reason = None
        if len(unique) == 1:
            reason = f"모든 항목 {scores[0]}점"
        elif avg <= 1.5:
            reason = "낮은 점수 집중"
        elif avg >= 4.8:
            reason = "높은 점수 집중"
        if reason:
            flags.append({
                "kind": kind,
                "evaluator": evaluator.name,
                "target": target,
                "average": round(avg, 2),
                "reason": reason,
            })

    team_evaluations = (
        TeamEvaluation.objects.filter(evaluation_round=evaluation_round, is_submitted=True)
        .select_related("evaluator__user", "target_team")
        .prefetch_related("scores")
    )
    for evaluation in team_evaluations:
        add_flag(
            "팀",
            evaluation.evaluator,
            evaluation.target_team.name,
            [item.score for item in evaluation.scores.all()],
        )

    personal_evaluations = (
        PersonalEvaluation.objects.filter(evaluation_round=evaluation_round, is_submitted=True)
        .select_related("evaluator__user", "target_student__user")
        .prefetch_related("scores")
    )
    for evaluation in personal_evaluations:
        add_flag(
            "개인",
            evaluation.evaluator,
            evaluation.target_student.name,
            [item.score for item in evaluation.scores.all()],
        )

    return flags


def build_evaluation_results_context(request):
    rounds = EvaluationRound.objects.all().order_by("-start_at")
    selected_round = _selected_round(request, rounds)
    query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "all")
    result_rows = []
    team_rows = []
    stats = {
        "team_completed": 0,
        "team_required": 0,
        "personal_completed": 0,
        "personal_required": 0,
        "calculated": 0,
        "excluded": 0,
        "publish_status": "미공개",
        "publish_detail": "학생에게 아직 결과를 공개하지 않았습니다.",
        "completion_percent": 0,
        "top_score": None,
        "average_score": None,
    }
    setting = None
    review_flags = []
    review_flag_count = 0

    if selected_round:
        memberships_qs = TeamMembership.objects.filter(
            team__evaluation_round=selected_round,
            team__is_active=True,
            student__is_active=True,
        ).select_related("team", "student__user")
        memberships = {m.student_id: m.team for m in memberships_qs}
        member_count_by_team = {}
        for membership in memberships_qs:
            member_count_by_team[membership.team_id] = member_count_by_team.get(membership.team_id, 0) + 1

        active_teams = list(Team.objects.filter(evaluation_round=selected_round, is_active=True).order_by("name"))
        attendance_map = dict(
            RoundAttendance.objects.filter(
                evaluation_round=selected_round,
                student_id__in=[m.student_id for m in memberships_qs],
            ).values_list("student_id", "status")
        )

        official_progress = _official_raw_progress(selected_round)
        if official_progress:
            stats.update(official_progress)
        else:
            stats.update(_submission_progress(selected_round, memberships_qs, active_teams, attendance_map))

        required_total = stats["team_required"] + stats["personal_required"]
        completed_total = min(stats["team_completed"], stats["team_required"]) + min(
            stats["personal_completed"], stats["personal_required"]
        )
        stats["completion_percent"] = round((completed_total / required_total) * 100) if required_total else 0

        all_review_flags = _evaluation_review_flags(selected_round)
        review_flag_count = len(all_review_flags)
        review_flags = all_review_flags[:12]

        results = StudentResult.objects.filter(evaluation_round=selected_round).select_related("student__user")
        if query:
            results = results.filter(
                Q(student__user__first_name__icontains=query)
                | Q(student__user__last_name__icontains=query)
                | Q(student__user__email__icontains=query)
                | Q(student__user__username__icontains=query)
                | Q(student__team_memberships__team__name__icontains=query)
            ).distinct()
        if status_filter == "included":
            results = results.filter(is_excluded=False)
        elif status_filter == "excluded":
            results = results.filter(is_excluded=True)
        results = results.order_by("is_excluded", "rank", "student__user__first_name", "student__user__username")

        for result in results:
            team = memberships.get(result.student_id)
            result_rows.append({
                "student_name": result.student.name,
                "email": result.student.user.email,
                "team_name": team.name if team else "-",
                "team_score": result.team_score,
                "personal_score": result.personal_score,
                "base_score": result.base_score,
                "adjustment_score": result.adjustment_score,
                "adjustment_reason": result.adjustment_reason,
                "result_id": result.id,
                "final_score": result.final_score,
                "rank": result.rank if not result.is_excluded else None,
                "is_excluded": result.is_excluded,
            })

        all_results = StudentResult.objects.filter(evaluation_round=selected_round)
        included_results = all_results.filter(is_excluded=False)
        stats["calculated"] = included_results.count()
        stats["excluded"] = all_results.filter(is_excluded=True).count()
        stats["average_score"] = included_results.aggregate(avg=Avg("final_score"))["avg"]
        top_result = included_results.order_by("rank", "-final_score").select_related("student__user").first()
        if top_result:
            stats["top_score"] = top_result.final_score
            stats["top_student"] = top_result.student.name

        team_eval_counts = dict(
            TeamEvaluation.objects.filter(evaluation_round=selected_round, is_submitted=True)
            .values("target_team_id").annotate(c=Count("id")).values_list("target_team_id", "c")
        )
        team_result_map = {result.team_id: result for result in TeamResult.objects.filter(evaluation_round=selected_round)}
        for team in active_teams:
            team_result = team_result_map.get(team.id)
            team_rows.append({
                "name": team.name,
                "member_count": member_count_by_team.get(team.id, 0),
                "evaluation_count": team_eval_counts.get(team.id, 0),
                "score": team_result.score if team_result else None,
                "rank": team_result.rank if team_result and not team_result.is_excluded else None,
                "is_excluded": team_result.is_excluded if team_result else False,
            })

        setting = ResultPublishSetting.objects.filter(evaluation_round=selected_round).first()
        if setting:
            now = timezone.now()
            if setting.is_published or (setting.publish_at and setting.publish_at <= now):
                stats["publish_status"] = "공개 중"
                stats["publish_detail"] = "학생 결과 화면에서 현재 결과를 확인할 수 있습니다."
            elif setting.publish_at and setting.publish_at > now:
                stats["publish_status"] = "예약 공개"
                stats["publish_detail"] = f"{timezone.localtime(setting.publish_at).strftime('%Y-%m-%d %H:%M')} 공개 예정"

    return {
        "rounds": rounds,
        "selected_round": selected_round,
        "result_rows": result_rows,
        "team_rows": team_rows,
        "stats": stats,
        "setting": setting,
        "query": query,
        "status_filter": status_filter,
        "review_flags": review_flags,
        "review_flag_count": review_flag_count,
    }
