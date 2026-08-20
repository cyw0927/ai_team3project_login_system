"""Compatibility shim for assignment submission requests.

The current assignment page posts an explicit ``assignment_id`` for each card.
Older clients/tests posted only the submission fields.  Keep those requests
safe: when the current round has exactly one assignment, resolve it
unambiguously; otherwise pass an impossible id so the original view returns a
normal 404 instead of raising ``ValueError`` for ``pk=''``.
"""

from .common import Assignment, _display_round_for_student
from .student import student_assignment_info as _student_assignment_info


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
