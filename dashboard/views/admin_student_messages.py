from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from .common import _redirect_back, admin_required
from ..models import Announcement, InternalMessage, Student


def _message_fields(request):
    title = (request.POST.get("title") or "").strip()
    body = (request.POST.get("body") or "").strip()
    priority = (request.POST.get("priority") or InternalMessage.Priority.NORMAL).strip()
    if priority not in InternalMessage.Priority.values:
        priority = Announcement.Priority.NORMAL
    return title, body, priority


def _validate_message(request, title, body):
    if not title or not body:
        messages.error(request, "메시지 제목과 내용을 모두 입력해주세요.")
        return False
    if len(title) > 160:
        messages.error(request, "메시지 제목은 160자 이하로 입력해주세요.")
        return False
    if len(body) > 5000:
        messages.error(request, "메시지 내용은 5,000자 이하로 입력해주세요.")
        return False
    return True


@admin_required
@require_POST
@transaction.atomic
def admin_students_bulk_message_send(request):
    student_ids = []
    for raw_id in request.POST.getlist("student_ids"):
        try:
            student_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue
    student_ids = list(dict.fromkeys(student_ids))
    if not student_ids:
        messages.error(request, "메시지를 받을 학생을 한 명 이상 선택해주세요.")
        return _redirect_back(request, "admin_students")

    students = list(
        Student.objects.select_related("user")
        .filter(id__in=student_ids)
        .order_by("user__first_name", "user__username")
    )
    if not students:
        messages.error(request, "선택한 학생 정보를 찾을 수 없습니다.")
        return _redirect_back(request, "admin_students")

    title, body, priority = _message_fields(request)
    if not _validate_message(request, title, body):
        return _redirect_back(request, "admin_students")

    InternalMessage.objects.bulk_create([
        InternalMessage(
            recipient=student,
            sender=request.user,
            title=title,
            body=body,
            priority=priority,
        )
        for student in students
    ])
    messages.success(request, f"선택한 {len(students)}명에게 시스템 메시지를 보냈습니다.")
    return _redirect_back(request, "admin_students")


@admin_required
@require_POST
@transaction.atomic
def admin_student_message_send(request, student_id):
    student = get_object_or_404(Student.objects.select_related("user"), pk=student_id)
    title, body, priority = _message_fields(request)
    if not _validate_message(request, title, body):
        return _redirect_back(request, "admin_students")

    InternalMessage.objects.create(
        recipient=student,
        sender=request.user,
        title=title,
        body=body,
        priority=priority,
    )
    messages.success(request, f"{student.name} 학생에게 시스템 메시지를 보냈습니다.")
    return _redirect_back(request, "admin_students")
