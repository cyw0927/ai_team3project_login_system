from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from .common import _redirect_back, admin_required
from ..models import (
    EvaluationRound,
    PersonalEvaluationScore,
    Student,
    TeamEvaluationScore,
    TeamMembership,
)
from ..services.result_service import recalculate_round_results
from ..services.seed_service import cumulative_seed_scores_before, previous_round_for
from ..services.team_assignment_service import (
    balanced_random_assignment,
    normalize_pot_cutoffs,
    pot_count_preview,
    pot_seed_assignment,
    snake_seed_assignment,
)


def _posted_pot_cutoffs(request):
    raw = (
        request.POST.get("pot_a_cutoff", "20"),
        request.POST.get("pot_b_cutoff", "50"),
        request.POST.get("pot_c_cutoff", "80"),
    )
    return normalize_pot_cutoffs(raw)


@admin_required
@require_POST
def admin_auto_preview(request):
    round_id = request.POST.get("round_id")
    evaluation_round = get_object_or_404(EvaluationRound, pk=round_id)

    try:
        team_count = int(request.POST.get("team_count", "0"))
    except ValueError:
        team_count = 0
    if team_count < 1:
        messages.error(request, "팀 수는 1개 이상이어야 합니다.")
        return _redirect_back(request, f"/management/team-assignment/?round={round_id}&tab=auto")

    students = list(
        Student.objects.filter(is_active=True, user__is_active=True).select_related("user")
    )
    if not students:
        messages.error(request, "편성할 활성 수강생이 없습니다.")
        return _redirect_back(request, f"/management/team-assignment/?round={round_id}&tab=auto")
    if team_count > len(students):
        messages.error(request, "팀 수는 활성 수강생 수보다 많을 수 없습니다.")
        return _redirect_back(request, f"/management/team-assignment/?round={round_id}&tab=auto")

    assignment_rule = request.POST.get("assignment_rule", "seed")
    avoid_previous = request.POST.get("avoid_previous", "1")
    try:
        pot_cutoffs = _posted_pot_cutoffs(request)
    except ValueError as exc:
        messages.error(request, str(exc))
        return _redirect_back(request, f"/management/team-assignment/?round={round_id}&tab=auto")

    previous_team_map = {}
    if avoid_previous == "1":
        previous_round = previous_round_for(evaluation_round)
        if previous_round:
            previous_team_map = dict(
                TeamMembership.objects.filter(team__evaluation_round=previous_round)
                .values_list("student_id", "team_id")
            )

    request.session["team_assignment_auto_settings"] = {
        "round_id": evaluation_round.id,
        "team_count": team_count,
        "assignment_rule": assignment_rule,
        "avoid_previous": avoid_previous,
        "pot_a_cutoff": pot_cutoffs[0],
        "pot_b_cutoff": pot_cutoffs[1],
        "pot_c_cutoff": pot_cutoffs[2],
    }
    request.session.modified = True

    seed_scores = {}
    previous_round = previous_round_for(evaluation_round)
    if assignment_rule in {"seed", "pot"} and previous_round:
        previous_rounds = EvaluationRound.objects.filter(
            start_at__lt=evaluation_round.start_at,
            status=EvaluationRound.Status.ENDED,
        ).order_by("start_at")
        for prior_round in previous_rounds:
            has_raw_scores = (
                TeamEvaluationScore.objects.filter(evaluation__evaluation_round=prior_round).exists()
                or PersonalEvaluationScore.objects.filter(evaluation__evaluation_round=prior_round).exists()
            )
            if has_raw_scores:
                recalculate_round_results(prior_round)
        seed_scores = cumulative_seed_scores_before(evaluation_round)

    grade_map = {}
    pot_counts = {}
    if assignment_rule == "seed" and seed_scores:
        buckets = snake_seed_assignment(students, team_count, seed_scores)
        messages.info(request, "이전 평가들의 누적 Seed를 기준으로 Z식 균형 편성을 적용했습니다.")
    elif assignment_rule == "pot" and seed_scores:
        buckets, grade_map, pot_counts = pot_seed_assignment(
            students,
            team_count,
            seed_scores,
            previous_team_map,
            pot_cutoffs=pot_cutoffs,
        )
        messages.info(
            request,
            f"포트 기준 A 0~{pot_cutoffs[0]}% / B {pot_cutoffs[0]}~{pot_cutoffs[1]}% / "
            f"C {pot_cutoffs[1]}~{pot_cutoffs[2]}% / D {pot_cutoffs[2]}~100%를 적용했습니다.",
        )
    else:
        if assignment_rule in {"seed", "pot"}:
            messages.warning(
                request,
                "이 회차보다 이전의 종료 성적이 없어 A/B/C/D 포트를 실제로 적용할 수 없습니다. "
                "현재 미리보기는 균등 랜덤입니다. AX2 2차 프로젝트 결과는 다음 회차를 만들면 Seed로 사용됩니다.",
            )
        buckets = balanced_random_assignment(students, team_count, previous_team_map)

    seed_rank_map = {}
    if seed_scores:
        ranked_students = sorted(
            [student for student in students if student.id in seed_scores],
            key=lambda student: (float(seed_scores[student.id]), -student.id),
            reverse=True,
        )
        seed_rank_map = {
            student.id: rank
            for rank, student in enumerate(ranked_students, start=1)
        }

    seed_number_map = {
        student_id: ((rank - 1) // team_count) + 1
        for student_id, rank in seed_rank_map.items()
    }

    preview = []
    for idx, bucket in enumerate(buckets, start=1):
        members = [
            {
                "name": student.name,
                "seed_rank": seed_rank_map.get(student.id),
                "seed_number": seed_number_map.get(student.id),
                "seed_score": float(seed_scores[student.id]) if student.id in seed_scores else None,
                "pot_grade": grade_map.get(student.id),
            }
            for student in bucket
        ]
        team_pot_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "U": 0}
        if assignment_rule == "pot":
            for member in members:
                grade = member.get("pot_grade")
                if grade in team_pot_counts:
                    team_pot_counts[grade] += 1

        preview.append({
            "name": f"{idx}팀",
            "student_ids": [student.id for student in bucket],
            "members": members,
            "pot_counts": team_pot_counts,
            "pot_cutoffs": list(pot_cutoffs),
            "pot_expected_counts": pot_count_preview(len(seed_scores), pot_cutoffs) if seed_scores else {},
            "assignment_rule": assignment_rule,
            "seed_available": bool(seed_scores),
        })

    request.session["team_assignment_preview"] = preview
    request.session["team_assignment_round_id"] = evaluation_round.id
    request.session.modified = True
    messages.success(request, "자동 편성 미리보기를 만들었습니다. 확정 전까지 DB에는 반영되지 않습니다.")
    return _redirect_back(request, f"/management/team-assignment/?round={round_id}&tab=auto#auto")
