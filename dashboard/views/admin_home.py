from django.shortcuts import render

from ..services.admin_dashboard_service import build_admin_dashboard_context
from .common import _base_context, _current_round, _sync_round_statuses, admin_required


@admin_required
def admin_dashboard(request):
    _sync_round_statuses()
    context = build_admin_dashboard_context(_current_round())
    return render(request, "admin_ui/dashboard.html", _base_context(**context))
