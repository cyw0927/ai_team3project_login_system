"""Thin admin views for assignment CRUD."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .common import _base_context, _redirect_back, _sync_round_statuses, admin_required
from ..models import Assignment, Skill
from ..services.assignment_service import (
    assignment_editable,
    assignment_form,
    assignment_rows,
    delete_assignment,
    editable_rounds,
    parse_assignment_skills,
    save_assignment,
)


def _show_errors(request, errors):
    for error in errors:
        messages.error(request, error)


@admin_required
def admin_assignments(request):
    _sync_round_statuses()
    return render(
        request,
        "admin_ui/assignments.html",
        _base_context(
            assignments=assignment_rows(),
            rounds=editable_rounds(),
            skills=Skill.objects.all(),
        ),
    )


@admin_required
def admin_assignment_create(request):
    if request.method != "POST":
        return redirect(f"{reverse('admin_assignments')}?open=create")

    form = assignment_form(request.POST, request.FILES)
    if not form.is_valid():
        _show_errors(request, [error for errors in form.errors.values() for error in errors])
        return _redirect_back(request, "admin_assignments")

    evaluation_round = form.cleaned_data["evaluation_round"]
    if evaluation_round not in editable_rounds():
        messages.error(request, "과제는 회차 시작 전부터 진행 중 평가 시작 전까지만 등록할 수 있습니다.")
        return _redirect_back(request, "admin_assignments")

    parsed_skills, errors = parse_assignment_skills(request.POST)
    if errors:
        _show_errors(request, errors)
        return _redirect_back(request, "admin_assignments")

    assignment = save_assignment(form, parsed_skills)
    messages.success(request, f"{assignment.title} 과제를 등록했습니다.")
    return _redirect_back(request, "admin_assignments")


@admin_required
def admin_assignment_update(request, assignment_id):
    assignment = get_object_or_404(
        Assignment.objects.select_related("evaluation_round"),
        pk=assignment_id,
    )
    if request.method != "POST":
        return redirect(f"{reverse('admin_assignments')}?edit={assignment.id}")
    if not assignment_editable(assignment):
        messages.error(request, "과제는 회차 시작 전부터 진행 중 평가 시작 전까지만 수정할 수 있습니다.")
        return _redirect_back(request, "admin_assignments")

    form = assignment_form(request.POST, request.FILES, instance=assignment)
    if not form.is_valid():
        _show_errors(request, [error for errors in form.errors.values() for error in errors])
        return _redirect_back(request, "admin_assignments")

    target_round = form.cleaned_data["evaluation_round"]
    if target_round not in editable_rounds():
        messages.error(request, "과제는 회차 시작 전부터 진행 중 평가 시작 전 상태에서만 수정할 수 있습니다.")
        return _redirect_back(request, "admin_assignments")

    parsed_skills, errors = parse_assignment_skills(request.POST)
    if errors:
        _show_errors(request, errors)
        return _redirect_back(request, "admin_assignments")

    assignment = save_assignment(form, parsed_skills)
    messages.success(request, f"{assignment.title} 과제를 수정했습니다.")
    return _redirect_back(request, "admin_assignments")


@admin_required
@require_POST
def admin_assignment_delete(request, assignment_id):
    assignment = get_object_or_404(
        Assignment.objects.select_related("evaluation_round"),
        pk=assignment_id,
    )
    if not assignment_editable(assignment):
        messages.error(request, "과제는 회차 시작 전부터 진행 중 평가 시작 전까지만 삭제할 수 있습니다.")
        return _redirect_back(request, "admin_assignments")

    title = assignment.title
    if not delete_assignment(assignment):
        messages.error(request, "현재 상태에서는 과제를 삭제할 수 없습니다.")
        return _redirect_back(request, "admin_assignments")

    messages.success(request, f"{title} 과제를 삭제했습니다.")
    return _redirect_back(request, "admin_assignments")
