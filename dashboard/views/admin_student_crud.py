import secrets
import string
import uuid

from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from .common import (
    _current_round,
    _invalidate_user_sessions,
    _redirect_back,
    _round_teams,
    _sync_student_team,
    admin_required,
)
from .admin_skills import _sync_student_common_skills
from ..forms import StudentCreateForm, StudentUpdateForm
from ..models import Student


@admin_required
@require_POST
@transaction.atomic
def admin_student_create(request):
    current_round = _current_round()
    teams = _round_teams(current_round)
    form = StudentCreateForm(request.POST, teams=teams)

    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return _redirect_back(request, "admin_students")

    name = form.cleaned_data["name"].strip()
    email = form.cleaned_data["email"]
    password = form.cleaned_data["password"]
    is_active = form.cleaned_data["is_active"]
    username = email or f"student_{uuid.uuid4().hex[:16]}"

    user = User(
        username=username,
        email=email,
        first_name=name,
        is_active=is_active,
    )
    if password:
        user.set_password(password)
    else:
        user.set_unusable_password()
    user.save()

    student = Student.objects.create(
        user=user,
        affiliation=form.cleaned_data["affiliation"].strip(),
        is_active=is_active,
    )
    _sync_student_common_skills(student)
    _sync_student_team(student, form.cleaned_data["team_id"], current_round)

    messages.success(request, f"{student.name} 수강생을 등록했습니다.")
    return _redirect_back(request, "admin_students")


@admin_required
@require_POST
@transaction.atomic
def admin_student_update(request, student_id):
    student = get_object_or_404(Student.objects.select_related("user"), pk=student_id)
    current_round = _current_round()
    teams = _round_teams(current_round)
    form = StudentUpdateForm(request.POST, student=student, teams=teams)

    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return _redirect_back(request, "admin_students")

    user = student.user
    submitted_email = form.cleaned_data["email"]
    is_active = form.cleaned_data["is_active"]

    user.first_name = form.cleaned_data["name"].strip()
    user.last_name = ""
    if submitted_email:
        user.email = submitted_email
        user.username = submitted_email
    user.is_active = is_active
    if form.cleaned_data["password"]:
        user.set_password(form.cleaned_data["password"])
    user.save()

    student.affiliation = form.cleaned_data["affiliation"].strip()
    student.is_active = is_active
    student.save()
    _sync_student_team(student, form.cleaned_data["team_id"], current_round)

    messages.success(request, f"{student.name} 수강생 정보를 수정했습니다.")
    return _redirect_back(request, "admin_students")


@admin_required
@require_POST
@transaction.atomic
def admin_student_toggle_active(request, student_id):
    student = get_object_or_404(Student.objects.select_related("user"), pk=student_id)
    new_state = not (student.is_active and student.user.is_active)
    student.is_active = new_state
    student.save(update_fields=["is_active", "updated_at"])
    student.user.is_active = new_state
    student.user.save(update_fields=["is_active"])

    state_label = "활성화" if new_state else "비활성화"
    messages.success(request, f"{student.name} 수강생을 {state_label}했습니다.")
    return _redirect_back(request, "admin_students")


@admin_required
@require_POST
@transaction.atomic
def admin_student_reset_password(request, student_id):
    student = get_object_or_404(Student.objects.select_related("user"), pk=student_id)
    new_password = (request.POST.get("new_password") or "").strip()
    generated = False
    if not new_password:
        alphabet = string.ascii_letters + string.digits
        new_password = (
            secrets.choice(string.ascii_uppercase)
            + secrets.choice(string.ascii_lowercase)
            + secrets.choice(string.digits)
            + "".join(secrets.choice(alphabet) for _ in range(9))
        )
        generated = True
    if len(new_password) < 8:
        messages.error(request, "임시 비밀번호는 8자 이상이어야 합니다.")
        return _redirect_back(request, "admin_students")

    student.user.set_password(new_password)
    student.user.save(update_fields=["password"])
    _invalidate_user_sessions(student.user_id)

    if generated:
        messages.success(request, f"{student.name}의 비밀번호를 초기화했습니다. 임시 비밀번호: {new_password}")
    else:
        messages.success(request, f"{student.name}의 비밀번호를 입력한 값으로 초기화했습니다.")
    return _redirect_back(request, "admin_students")


@admin_required
@require_POST
@transaction.atomic
def admin_student_delete(request, student_id):
    student = get_object_or_404(Student.objects.select_related("user"), pk=student_id)
    name = student.name
    student.user.delete()
    messages.success(request, f"{name} 수강생을 삭제했습니다.")
    return _redirect_back(request, "admin_students")
