from django.shortcuts import render

from ..services.student_result_service import build_student_result_context
from .common import _base_context, student_required


@student_required
def student_results(request):
    """학생 본인에게 공개된 결과를 회차별로 선택해서 보여준다."""
    context = build_student_result_context(
        request.student,
        selected_round_id=request.GET.get("round", ""),
    )
    return render(
        request,
        "student/results.html",
        _base_context(**context),
    )
