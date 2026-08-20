"""Assignment management rules used by admin views."""

from django.db import transaction
from django.db.models import Q

from ..forms import AssignmentForm
from ..models import Assignment, AssignmentSkill, EvaluationRound, Skill


def editable_rounds():
    return EvaluationRound.objects.filter(
        Q(status=EvaluationRound.Status.SCHEDULED)
        | Q(status=EvaluationRound.Status.IN_PROGRESS, evaluation_started=False)
    ).order_by("-start_at")


def assignment_editable(assignment):
    round_obj = assignment.evaluation_round
    return (
        round_obj.status in {
            EvaluationRound.Status.SCHEDULED,
            EvaluationRound.Status.IN_PROGRESS,
        }
        and not round_obj.evaluation_started
    )


def assignment_rows():
    rows = list(
        Assignment.objects.select_related("evaluation_round")
        .prefetch_related("required_skills__skill")
        .order_by("-evaluation_round__start_at")
    )
    for assignment in rows:
        assignment.round_name = assignment.evaluation_round.name
        assignment.deadline = assignment.evaluation_round.end_at
        assignment.status_display = assignment.evaluation_round.get_status_display()
        assignment.can_edit = assignment_editable(assignment)
        assignment.can_delete = assignment.can_edit
        assignment.skill_items = list(assignment.required_skills.all())
        assignment.skill_weight_total = sum(item.weight for item in assignment.skill_items)
        if assignment.attachment:
            assignment.attachment_url = assignment.attachment.url
            assignment.attachment_name = assignment.attachment.name.rsplit("/", 1)[-1]
        else:
            assignment.attachment_url = ""
            assignment.attachment_name = ""
    return rows


def parse_assignment_skills(post_data):
    skill_ids = post_data.getlist("skill_id")
    weights = post_data.getlist("skill_weight")
    parsed = []
    used = set()
    errors = []

    for raw_skill_id, raw_weight in zip(skill_ids, weights):
        raw_skill_id = (raw_skill_id or "").strip()
        raw_weight = (raw_weight or "").strip()
        if not raw_skill_id:
            continue
        try:
            skill_id = int(raw_skill_id)
            weight = int(raw_weight)
        except (TypeError, ValueError):
            errors.append("역량과 중요도는 올바른 숫자로 입력해주세요.")
            continue
        if skill_id in used:
            errors.append("같은 역량을 중복으로 선택할 수 없습니다.")
            continue
        if weight < 1 or weight > 100:
            errors.append("역량 중요도는 1~100 사이여야 합니다.")
            continue
        used.add(skill_id)
        parsed.append((skill_id, weight))

    if parsed and sum(weight for _, weight in parsed) != 100:
        errors.append("필요 역량 중요도의 합계는 100%여야 합니다.")

    existing_ids = set(
        Skill.objects.filter(id__in=[skill_id for skill_id, _ in parsed])
        .values_list("id", flat=True)
    )
    if len(existing_ids) != len(parsed):
        errors.append("선택한 역량 중 존재하지 않는 항목이 있습니다.")

    return parsed, errors


def assignment_form(post_data, files, *, instance=None):
    return AssignmentForm(
        post_data,
        files,
        instance=instance,
        rounds=editable_rounds(),
    )


@transaction.atomic
def save_assignment(form, parsed_skills):
    assignment = form.save()
    AssignmentSkill.objects.filter(assignment=assignment).delete()
    AssignmentSkill.objects.bulk_create([
        AssignmentSkill(
            assignment=assignment,
            skill_id=skill_id,
            weight=weight,
        )
        for skill_id, weight in parsed_skills
    ])
    return assignment


@transaction.atomic
def delete_assignment(assignment):
    if not assignment_editable(assignment):
        return False
    assignment.delete()
    return True
