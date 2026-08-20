"""Admin evaluation-template views.

Result, score, ranking, missing-evaluation, publication, export and Seed screens
live in dedicated view/service modules. This module now owns only template and
criterion management.
"""

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .common import _base_context, _redirect_back, admin_required
from ..forms import EvaluationCriterionForm, EvaluationTemplateForm
from ..models import EvaluationCriterion, EvaluationRound, EvaluationTemplate


def _template_url(template):
    """수정/추가 후 현재 평가 유형 탭과 선택 템플릿을 유지한다."""
    return (
        "/management/evaluation-templates/"
        f"?type={template.evaluation_type}&template={template.id}"
    )


def _show_form_errors(request, form):
    for errors in form.errors.values():
        for error in errors:
            messages.error(request, error)


@admin_required
def admin_evaluation_templates(request):
    selected_template_id = request.GET.get("template", "").strip()
    type_filter = request.GET.get("type", "team").strip()
    valid_types = {
        EvaluationTemplate.EvaluationType.TEAM,
        EvaluationTemplate.EvaluationType.PERSONAL,
    }
    if type_filter not in valid_types:
        type_filter = EvaluationTemplate.EvaluationType.TEAM

    templates = list(
        EvaluationTemplate.objects.filter(evaluation_round__isnull=True)
        .select_related("evaluation_round")
        .prefetch_related("criteria")
        .order_by("evaluation_type", "name")
    )
    for template in templates:
        template.type_display = template.get_evaluation_type_display()
        template.status_display = "사용 중" if template.is_active else "비활성"
        template.criterion_count = template.criteria.count()

    filtered_templates = [
        template for template in templates if template.evaluation_type == type_filter
    ]
    selected_template = None
    if selected_template_id:
        selected_template = next(
            (
                template
                for template in filtered_templates
                if str(template.id) == selected_template_id
            ),
            None,
        )
    if selected_template is None and filtered_templates:
        selected_template = filtered_templates[0]

    criteria = (
        list(selected_template.criteria.all().order_by("order", "id"))
        if selected_template
        else []
    )
    rounds = EvaluationRound.objects.all().order_by("-start_at")
    stats = {
        "total": len(templates),
        "team": sum(
            template.evaluation_type == EvaluationTemplate.EvaluationType.TEAM
            for template in templates
        ),
        "personal": sum(
            template.evaluation_type == EvaluationTemplate.EvaluationType.PERSONAL
            for template in templates
        ),
        "active": sum(template.is_active for template in templates),
    }
    return render(
        request,
        "admin_ui/evaluation_templates.html",
        _base_context(
            evaluation_templates=templates,
            filtered_templates=filtered_templates,
            selected_template=selected_template,
            criteria=criteria,
            rounds=rounds,
            stats=stats,
            type_filter=type_filter,
            required_count=sum(criterion.is_required for criterion in criteria),
            optional_count=sum(not criterion.is_required for criterion in criteria),
        ),
    )


@admin_required
@require_POST
@transaction.atomic
def admin_evaluation_template_create(request):
    form = EvaluationTemplateForm(request.POST, rounds=EvaluationRound.objects.all())
    if not form.is_valid():
        _show_form_errors(request, form)
        return _redirect_back(request, "admin_evaluation_templates")
    template = form.save()
    messages.success(request, f"{template.name} 템플릿을 생성했습니다.")
    return redirect(_template_url(template))


@admin_required
@require_POST
@transaction.atomic
def admin_evaluation_template_update(request, template_id):
    template = get_object_or_404(EvaluationTemplate, pk=template_id)
    form = EvaluationTemplateForm(
        request.POST,
        instance=template,
        rounds=EvaluationRound.objects.all(),
    )
    if not form.is_valid():
        _show_form_errors(request, form)
        return redirect(_template_url(template))
    template = form.save()
    messages.success(request, f"{template.name} 템플릿을 수정했습니다.")
    return redirect(_template_url(template))


@admin_required
@require_POST
@transaction.atomic
def admin_evaluation_template_toggle(request, template_id):
    template = get_object_or_404(EvaluationTemplate, pk=template_id)
    template.is_active = not template.is_active
    template.save(update_fields=["is_active", "updated_at"])
    messages.success(request, f"{template.name} 템플릿 상태를 변경했습니다.")
    return redirect(_template_url(template))


@admin_required
@require_POST
@transaction.atomic
def admin_evaluation_template_delete(request, template_id):
    template = get_object_or_404(EvaluationTemplate, pk=template_id)
    used = (
        template.criteria.filter(team_scores__isnull=False).exists()
        or template.criteria.filter(personal_scores__isnull=False).exists()
    )
    if used:
        messages.error(request, "이미 평가에 사용된 템플릿은 삭제할 수 없습니다. 비활성화하세요.")
        return redirect(_template_url(template))
    name = template.name
    template.delete()
    messages.success(request, f"{name} 템플릿을 삭제했습니다.")
    return _redirect_back(request, "admin_evaluation_templates")


@admin_required
@require_POST
@transaction.atomic
def admin_evaluation_criterion_create(request, template_id):
    template = get_object_or_404(EvaluationTemplate, pk=template_id)
    form = EvaluationCriterionForm(request.POST)
    if not form.is_valid():
        _show_form_errors(request, form)
        return redirect(_template_url(template))
    criterion = form.save(commit=False)
    criterion.template = template
    if not request.POST.get("order"):
        last = template.criteria.order_by("-order", "-id").first()
        criterion.order = (last.order + 1) if last else 1
    criterion.save()
    messages.success(request, f"{criterion.title} 문항을 추가했습니다.")
    return redirect(_template_url(template))


@admin_required
@require_POST
@transaction.atomic
def admin_evaluation_criterion_update(request, criterion_id):
    criterion = get_object_or_404(
        EvaluationCriterion.objects.select_related("template"),
        pk=criterion_id,
    )
    form = EvaluationCriterionForm(request.POST, instance=criterion)
    if not form.is_valid():
        _show_form_errors(request, form)
        return redirect(_template_url(criterion.template))
    criterion = form.save()
    messages.success(request, f"{criterion.title} 문항을 수정했습니다.")
    return redirect(_template_url(criterion.template))


@admin_required
@require_POST
@transaction.atomic
def admin_evaluation_criterion_delete(request, criterion_id):
    criterion = get_object_or_404(
        EvaluationCriterion.objects.select_related("template"),
        pk=criterion_id,
    )
    if criterion.team_scores.exists() or criterion.personal_scores.exists():
        messages.error(request, "이미 평가에 사용된 문항은 삭제할 수 없습니다.")
        return redirect(_template_url(criterion.template))
    title = criterion.title
    template = criterion.template
    criterion.delete()
    messages.success(request, f"{title} 문항을 삭제했습니다.")
    return redirect(_template_url(template))


@admin_required
@require_POST
@transaction.atomic
def admin_evaluation_criterion_move(request, criterion_id, direction):
    criterion = get_object_or_404(
        EvaluationCriterion.objects.select_related("template"),
        pk=criterion_id,
    )
    siblings = list(criterion.template.criteria.all().order_by("order", "id"))
    try:
        index = next(
            i for i, item in enumerate(siblings) if item.id == criterion.id
        )
    except StopIteration:
        return redirect(_template_url(criterion.template))

    if direction == "up":
        target_index = index - 1
    elif direction == "down":
        target_index = index + 1
    else:
        target_index = index

    if 0 <= target_index < len(siblings) and target_index != index:
        target = siblings[target_index]
        criterion.order, target.order = target.order, criterion.order
        criterion.save(update_fields=["order", "updated_at"])
        target.save(update_fields=["order", "updated_at"])
    return redirect(_template_url(criterion.template))


@admin_required
@require_POST
@transaction.atomic
def admin_evaluation_criteria_reorder(request, template_id):
    template = get_object_or_404(EvaluationTemplate, pk=template_id)
    raw_ids = request.POST.get("ordered_ids", "")
    try:
        ordered_ids = [
            int(value) for value in raw_ids.split(",") if value.strip()
        ]
    except ValueError:
        messages.error(request, "문항 순서 정보가 올바르지 않습니다.")
        return redirect(_template_url(template))

    existing_ids = list(
        template.criteria.order_by("order", "id").values_list("id", flat=True)
    )
    if sorted(ordered_ids) != sorted(existing_ids):
        messages.error(
            request,
            "문항 목록이 변경되어 순서를 저장하지 못했습니다. 새로고침 후 다시 시도해주세요.",
        )
        return redirect(_template_url(template))

    for index, criterion_id in enumerate(ordered_ids, start=1):
        EvaluationCriterion.objects.filter(
            pk=criterion_id,
            template=template,
        ).update(order=index)

    messages.success(request, "평가 문항 순서를 저장했습니다.")
    return redirect(_template_url(template))
