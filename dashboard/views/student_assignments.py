"""Student assignment submission and download views.

This module owns assignment I/O for students and keeps the small legacy POST
compatibility rule in the real view instead of a wrapper module.
"""

import re

from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .common import _base_context, _decorate_assignment, _display_round_for_student, _student_team, student_required
from ..models import (
    Assignment,
    EvaluationRound,
    StudentAssignmentSubmission,
    TeamAssignmentSubmission,
    TeamMembership,
)

_STORAGE_COLLISION_SUFFIX = re.compile(r"^(?P<stem>.+)_[A-Za-z0-9]{7}(?P<ext>\.[^.]+)$")


def _download_response(field_file):
    if not field_file:
        raise Http404("첨부파일이 없습니다.")
    try:
        file_handle = field_file.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("첨부파일을 찾을 수 없습니다.")

    stored_name = field_file.name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    collision = _STORAGE_COLLISION_SUFFIX.match(stored_name)
    filename = (
        f"{collision.group('stem')}{collision.group('ext')}"
        if collision
        else stored_name
    )
    return FileResponse(file_handle, as_attachment=True, filename=filename)


@student_required
@transaction.atomic
def student_assignment_info(request):
    """현재 회차의 조별/개별 과제를 조회하고 제출한다."""
    evaluation_round = _display_round_for_student()
    my_team = _student_team(request.student, evaluation_round) if evaluation_round else None
    can_submit = bool(
        evaluation_round
        and evaluation_round.status == EvaluationRound.Status.IN_PROGRESS
        and not evaluation_round.evaluation_started
        and not evaluation_round.is_locked
    )

    assignments = []
    if evaluation_round:
        assignments = list(
            Assignment.objects.filter(evaluation_round=evaluation_round)
            .select_related("evaluation_round")
            .order_by("assignment_type", "id")
        )
        for assignment in assignments:
            _decorate_assignment(assignment)

    if request.method == "POST":
        if not evaluation_round:
            messages.error(request, "현재 진행 중인 회차가 없습니다.")
            return redirect("student_assignment_info")
        if not can_submit:
            messages.error(request, "과제 제출은 회차 시작 후 평가 시작 전까지만 수정할 수 있습니다.")
            return redirect("student_assignment_info")

        raw_assignment_id = (request.POST.get("assignment_id") or "").strip()
        # Compatibility for older clients/tests that omitted assignment_id.
        if not raw_assignment_id:
            assignment_ids = list(
                Assignment.objects.filter(evaluation_round=evaluation_round)
                .order_by("id")
                .values_list("id", flat=True)[:2]
            )
            raw_assignment_id = str(assignment_ids[0]) if len(assignment_ids) == 1 else "0"

        assignment = get_object_or_404(
            Assignment,
            pk=raw_assignment_id,
            evaluation_round=evaluation_round,
        )
        submission_url = request.POST.get("submission_url", "").strip()
        note = request.POST.get("note", "").strip()
        attachment = request.FILES.get("attachment")

        if assignment.assignment_type == Assignment.AssignmentType.TEAM:
            if not my_team:
                messages.error(request, "조별과제 제출을 위해 먼저 팀에 배정되어야 합니다.")
                return redirect("student_assignment_info")
            submission = TeamAssignmentSubmission.objects.filter(
                assignment=assignment,
                team=my_team,
            ).first()
            if not submission_url and not note and not attachment and not (submission and submission.attachment):
                messages.error(request, "제출 링크, 파일, 메모 중 하나 이상을 입력해 주세요.")
                return redirect("student_assignment_info")
            submission, _ = TeamAssignmentSubmission.objects.get_or_create(
                assignment=assignment,
                team=my_team,
                defaults={"submitted_by": request.student},
            )
            submission.submitted_by = request.student
            success_label = f"{my_team.name} 조별과제"
        else:
            submission = StudentAssignmentSubmission.objects.filter(
                assignment=assignment,
                student=request.student,
            ).first()
            if not submission_url and not note and not attachment and not (submission and submission.attachment):
                messages.error(request, "제출 링크, 파일, 메모 중 하나 이상을 입력해 주세요.")
                return redirect("student_assignment_info")
            submission, _ = StudentAssignmentSubmission.objects.get_or_create(
                assignment=assignment,
                student=request.student,
            )
            success_label = "개별과제"

        submission.submission_url = submission_url
        submission.note = note
        if attachment:
            submission.attachment = attachment
        submission.submitted_at = timezone.now()
        submission.save()
        messages.success(request, f"{success_label} 제출 내용을 저장했습니다.")
        return redirect("student_assignment_info")

    rows = []
    for assignment in assignments:
        if assignment.assignment_type == Assignment.AssignmentType.TEAM:
            submission = None
            if my_team:
                submission = TeamAssignmentSubmission.objects.filter(
                    assignment=assignment,
                    team=my_team,
                ).select_related("submitted_by__user", "commented_by").first()
            rows.append({
                "assignment": assignment,
                "submission": submission,
                "is_team": True,
                "can_access": bool(my_team),
            })
        else:
            submission = StudentAssignmentSubmission.objects.filter(
                assignment=assignment,
                student=request.student,
            ).first()
            rows.append({
                "assignment": assignment,
                "submission": submission,
                "is_team": False,
                "can_access": True,
            })

    return render(
        request,
        "student/assignment_info.html",
        _base_context(
            evaluation_round=evaluation_round,
            assignment_rows=rows,
            my_team=my_team,
            can_submit=can_submit,
            presentation_schedule=[],
        ),
    )


@student_required
def assignment_attachment_download(request, assignment_id):
    assignment = get_object_or_404(Assignment, pk=assignment_id)
    return _download_response(assignment.attachment)


@student_required
def submission_attachment_download(request, submission_id):
    submission = get_object_or_404(
        TeamAssignmentSubmission.objects.select_related("team", "assignment__evaluation_round"),
        pk=submission_id,
    )
    if not TeamMembership.objects.filter(team=submission.team, student=request.student).exists():
        messages.error(request, "본인 팀의 제출파일만 다운로드할 수 있습니다.")
        return redirect("student_assignment_info")
    return _download_response(submission.attachment)


@student_required
def student_submission_attachment_download(request, submission_id):
    submission = get_object_or_404(
        StudentAssignmentSubmission.objects.select_related("student__user", "assignment__evaluation_round"),
        pk=submission_id,
        student=request.student,
    )
    return _download_response(submission.attachment)
