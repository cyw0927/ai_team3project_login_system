from urllib.parse import quote

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect

from .common import _current_round, admin_required
from ..models import EvaluationRound
from ..services.result_export_service import build_result_workbook
from ..services.result_service import recalculate_round_results


@admin_required
def admin_evaluation_results_excel_export(request):
    rounds = EvaluationRound.objects.all().order_by("-start_at")
    round_id = request.GET.get("round")
    selected_round = rounds.filter(pk=round_id).first() if round_id else _current_round()
    if not selected_round:
        messages.error(request, "내보낼 평가 회차가 없습니다.")
        return redirect("admin_evaluation_results")

    recalculate_round_results(selected_round)
    content = build_result_workbook(selected_round)
    filename = f"{selected_round.name}_평가결과.xlsx"
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return response
