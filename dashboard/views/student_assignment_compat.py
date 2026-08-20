"""Compatibility helpers for assignment submission/download requests.

The current assignment page posts an explicit ``assignment_id`` for each card.
Older clients/tests posted only the submission fields. Keep those requests safe:
when the current round has exactly one assignment, resolve it unambiguously;
otherwise pass an impossible id so the original view returns a normal 404
instead of raising ``ValueError`` for ``pk=''``.

Django's default storage appends a random 7-character suffix when a test/media
file with the same name already exists (for example ``guide_1Hh1V5z.txt``).
For download responses, hide only that storage collision suffix so users still
receive the original-looking filename (``guide.txt``).
"""

import re

from .common import Assignment, _display_round_for_student
from .student import (
    assignment_attachment_download as _assignment_attachment_download,
    student_assignment_info as _student_assignment_info,
)

_STORAGE_COLLISION_SUFFIX = re.compile(r"^(?P<stem>.+)_[A-Za-z0-9]{7}(?P<ext>\.[^.]+)$")


def student_assignment_info(request):
    if request.method == "POST" and not (request.POST.get("assignment_id") or "").strip():
        evaluation_round = _display_round_for_student()
        assignment_ids = []
        if evaluation_round:
            assignment_ids = list(
                Assignment.objects.filter(evaluation_round=evaluation_round)
                .order_by("id")
                .values_list("id", flat=True)[:2]
            )

        mutable_post = request.POST.copy()
        mutable_post["assignment_id"] = str(assignment_ids[0]) if len(assignment_ids) == 1 else "0"
        request.POST = mutable_post

    return _student_assignment_info(request)


def assignment_attachment_download(request, assignment_id):
    """Delegate auth/file handling, then normalize Django collision suffixes."""
    response = _assignment_attachment_download(request, assignment_id)
    disposition = response.get("Content-Disposition", "")
    match = re.search(r'filename="(?P<name>[^"]+)"', disposition)
    if not match:
        return response

    stored_name = match.group("name")
    collision = _STORAGE_COLLISION_SUFFIX.match(stored_name)
    if not collision:
        return response

    download_name = f"{collision.group('stem')}{collision.group('ext')}"
    response["Content-Disposition"] = disposition.replace(
        f'filename="{stored_name}"',
        f'filename="{download_name}"',
        1,
    )
    return response
