from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from .common import _redirect_back, admin_required
from ..models import StudentResult
from ..services.result_adjustment_service import parse_adjustment, save_adjustment


@admin_required
@require_POST
def admin_student_result_adjust(request, result_id):
    result = get_object_or_404(
        StudentResult.objects.select_related("evaluation_round", "student__user"),
        id=result_id,
    )
    adjustment, reason, error = parse_adjustment(
        request.POST.get("adjustment_score"),
        request.POST.get("adjustment_reason"),
    )
    if error:
        messages.error(request, error)
        return _redirect_back(request, "admin_evaluation_results")

    save_adjustment(result, adjustment, reason)
    messages.success(request, f"{result.student.name} 학생의 관리자 보정점수를 저장했습니다.")
    return _redirect_back(request, "admin_evaluation_results")
