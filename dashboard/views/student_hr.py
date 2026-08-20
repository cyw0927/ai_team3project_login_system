"""Student growth-task views."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .common import _base_context, student_required
from ..models import HRTask, HRTaskEvaluation, HRTaskStep, HRTaskSubmission


@login_required
def hr_task_attachment_download(request, task_id):
    task = get_object_or_404(HRTask.objects.select_related("assignee__user"), pk=task_id)

    if not (request.user.is_staff or request.user.is_superuser):
        student = getattr(request.user, "student_profile", None)
        if not student or not student.is_active or task.assignee_id != student.id:
            messages.error(request, "본인에게 배정된 역량 과제의 첨부파일만 받을 수 있습니다.")
            return redirect("student_hr_tasks")

    if not task.attachment:
        raise Http404("첨부파일이 없습니다.")

    try:
        file_handle = task.attachment.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("첨부파일을 찾을 수 없습니다.")

    filename = task.attachment.name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return FileResponse(file_handle, as_attachment=True, filename=filename)


@student_required
def student_hr_tasks(request):
    student = request.student
    tasks = list(
        HRTask.objects.filter(assignee=student)
        .select_related("evaluation_round")
        .prefetch_related("required_skills__skill", "steps")
        .order_by("status", "due_date", "-created_at")
    )
    for task in tasks:
        task.skill_items = list(task.required_skills.all())
        task.step_items = list(task.steps.all())
        task.submission_obj = HRTaskSubmission.objects.filter(task=task, student=student).first()
        task.evaluation_obj = HRTaskEvaluation.objects.filter(task=task, student=student).first()

    stats = {
        "total": len(tasks),
        "active": sum(1 for task in tasks if task.status == HRTask.Status.IN_PROGRESS),
        "review": sum(1 for task in tasks if task.status == HRTask.Status.REVIEW),
        "overdue": sum(1 for task in tasks if task.is_overdue),
    }
    return render(request, "student/hr_tasks.html", _base_context(tasks=tasks, task_stats=stats))


@student_required
@require_POST
@transaction.atomic
def student_hr_task_step_toggle(request, task_id, step_id):
    task = get_object_or_404(HRTask, pk=task_id, assignee=request.student)
    step = get_object_or_404(HRTaskStep, pk=step_id, task=task)

    if task.status in {HRTask.Status.REVIEW, HRTask.Status.COMPLETED}:
        messages.error(request, "검토 요청 또는 완료 상태의 과제는 Step을 수정할 수 없습니다.")
        return redirect("student_hr_tasks")

    step.is_completed = not step.is_completed
    step.completed_at = timezone.now() if step.is_completed else None
    step.save(update_fields=["is_completed", "completed_at", "updated_at"])

    if step.is_completed and task.status in {HRTask.Status.UNASSIGNED, HRTask.Status.SCHEDULED}:
        task.status = HRTask.Status.IN_PROGRESS
        task.save(update_fields=["status", "updated_at"])

    return redirect("student_hr_tasks")


@student_required
@require_POST
@transaction.atomic
def student_hr_task_submit(request, task_id):
    student = request.student
    task = get_object_or_404(HRTask.objects.prefetch_related("steps"), pk=task_id, assignee=student)

    if task.status == HRTask.Status.COMPLETED:
        messages.error(request, "이미 완료 처리된 과제입니다.")
        return redirect("student_hr_tasks")

    content = (request.POST.get("content") or "").strip()
    attachment = request.FILES.get("attachment")
    if not content and not attachment:
        messages.error(request, "제출 내용 또는 첨부파일 중 하나는 입력해주세요.")
        return redirect("student_hr_tasks")

    submission, _ = HRTaskSubmission.objects.get_or_create(
        task=task,
        defaults={"student": student},
    )
    submission.student = student
    submission.content = content
    if attachment:
        submission.attachment = attachment
    submission.submitted_at = timezone.now()
    submission.save()

    task.status = HRTask.Status.REVIEW
    task.save(update_fields=["status", "updated_at"])
    messages.success(
        request,
        "과제를 제출했습니다. Step 체크는 자기진도 기록이며 최종 완료는 튜터 평가 후 확정됩니다.",
    )
    return redirect("student_hr_tasks")
