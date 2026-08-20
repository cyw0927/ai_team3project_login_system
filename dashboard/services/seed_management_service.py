"""Admin Seed-management data preparation and weight validation."""

import math
from decimal import Decimal

from django.core.paginator import Paginator

from dashboard.models import EvaluationRound, Student, StudentResult
from dashboard.services.seed_service import cumulative_seed_scores_before


def parse_seed_weights(seed_weight_raw, team_weight_raw, personal_weight_raw):
    """Validate submitted Seed weights and return normalized integer values."""
    try:
        seed_weight = int(seed_weight_raw)
        seed_team_weight = int(team_weight_raw)
        seed_personal_weight = int(personal_weight_raw)
    except (TypeError, ValueError):
        return None, "Seed 설정값은 숫자로 입력해 주세요."

    if not 0 <= seed_weight <= 100:
        return None, "회차 반영 가중치는 0~100 사이여야 합니다."
    if not 0 <= seed_team_weight <= 100 or not 0 <= seed_personal_weight <= 100:
        return None, "팀/개인 Seed 비율은 각각 0~100 사이여야 합니다."
    if seed_team_weight + seed_personal_weight != 100:
        return None, "팀 Seed 비율과 개인 Seed 비율의 합은 100이어야 합니다."

    return {
        "seed_weight": seed_weight,
        "seed_team_weight": seed_team_weight,
        "seed_personal_weight": seed_personal_weight,
    }, None


def apply_seed_weights(evaluation_round, values):
    evaluation_round.seed_weight = values["seed_weight"]
    evaluation_round.seed_team_weight = values["seed_team_weight"]
    evaluation_round.seed_personal_weight = values["seed_personal_weight"]
    evaluation_round.save(
        update_fields=[
            "seed_weight",
            "seed_team_weight",
            "seed_personal_weight",
            "updated_at",
        ]
    )


def build_seed_management_context(selected_round, page_number=None):
    seed_rows = []
    history_rounds = []
    selected_round_results = []
    pot_summary = []

    if selected_round:
        history_rounds = list(
            EvaluationRound.objects.filter(
                start_at__lt=selected_round.start_at,
                status=EvaluationRound.Status.ENDED,
            ).order_by("-start_at", "-id")
        )

        seed_scores = cumulative_seed_scores_before(selected_round)
        students = (
            Student.objects.filter(id__in=seed_scores.keys())
            .select_related("user")
            .order_by("user__first_name", "user__username")
        )
        student_ids = list(seed_scores.keys())
        seed_breakdowns = {student_id: [] for student_id in student_ids}

        breakdown_results = (
            StudentResult.objects.filter(
                evaluation_round__in=history_rounds,
                student_id__in=student_ids,
                is_excluded=False,
            )
            .exclude(final_score__isnull=True)
            .select_related("evaluation_round")
            .order_by("evaluation_round__start_at", "evaluation_round_id")
        )

        for result in breakdown_results:
            round_obj = result.evaluation_round
            history_weight = int(round_obj.seed_weight or 0)
            team_weight = int(round_obj.seed_team_weight or 0)
            personal_weight = int(round_obj.seed_personal_weight or 0)
            score_weight_total = team_weight + personal_weight
            if history_weight <= 0 or score_weight_total <= 0:
                continue
            seed_base_score = (
                (result.team_score * Decimal(team_weight))
                + (result.personal_score * Decimal(personal_weight))
            ) / Decimal(score_weight_total)
            seed_breakdowns.setdefault(result.student_id, []).append({
                "round_name": round_obj.name,
                "start_at": round_obj.start_at,
                "team_score": result.team_score,
                "personal_score": result.personal_score,
                "team_weight": team_weight,
                "personal_weight": personal_weight,
                "round_weight": history_weight,
                "base_score": seed_base_score,
                "weighted_points": seed_base_score * Decimal(history_weight),
            })

        for student in students:
            detail_rows = seed_breakdowns.get(student.id, [])
            total_weight = sum(item["round_weight"] for item in detail_rows)
            weighted_total = sum((item["weighted_points"] for item in detail_rows), Decimal("0"))
            for item in detail_rows:
                item["contribution_score"] = (
                    item["weighted_points"] / Decimal(total_weight)
                    if total_weight else Decimal("0")
                )
            seed_rows.append({
                "student_id": student.id,
                "student_name": student.name,
                "email": student.user.email,
                "seed_score": seed_scores.get(student.id),
                "seed_total_weight": total_weight,
                "seed_weighted_total": weighted_total,
                "breakdown_rows": list(reversed(detail_rows)),
            })

        seed_rows.sort(key=lambda row: float(row["seed_score"] or 0), reverse=True)
        pot_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
        total_seed_rows = len(seed_rows)
        a_cut = math.ceil(total_seed_rows * 0.20) if total_seed_rows else 0
        b_cut = math.ceil(total_seed_rows * 0.30) if total_seed_rows else 0
        c_cut = math.ceil(total_seed_rows * 0.80) if total_seed_rows else 0

        for index, row in enumerate(seed_rows, start=1):
            row["seed_rank"] = index
            percentile = (index / total_seed_rows) * 100 if total_seed_rows else 100
            if index <= a_cut:
                pot_grade = "A"
            elif index <= b_cut:
                pot_grade = "B"
            elif index <= c_cut:
                pot_grade = "C"
            else:
                pot_grade = "D"
            row["pot_grade"] = pot_grade
            row["percentile"] = round(percentile, 1)
            pot_counts[pot_grade] += 1

        for grade, label, range_label in [
            ("A", "최상위 포트", "상위 20%"),
            ("B", "상위 포트", "20~30%"),
            ("C", "중간 포트", "30~80%"),
            ("D", "하위 포트", "80~100%"),
        ]:
            count = pot_counts[grade]
            pot_summary.append({
                "grade": grade,
                "label": label,
                "range_label": range_label,
                "count": count,
                "ratio": round((count / total_seed_rows) * 100, 1) if total_seed_rows else 0,
            })

        selected_round_results = list(
            StudentResult.objects.filter(
                evaluation_round=selected_round,
                is_excluded=False,
            ).select_related("student__user").order_by("rank", "-final_score")
        )

    seed_page_obj = None
    if seed_rows:
        seed_paginator = Paginator(seed_rows, 50)
        seed_page_obj = seed_paginator.get_page(page_number)
        seed_rows = list(seed_page_obj.object_list)

    return {
        "history_rounds": history_rounds,
        "seed_rows": seed_rows,
        "seed_page_obj": seed_page_obj,
        "pot_summary": pot_summary,
        "selected_round_results": selected_round_results,
    }
