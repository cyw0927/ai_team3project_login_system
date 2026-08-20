"""Admin skill dictionary management views."""

from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .common import _base_context, admin_required
from ..models import AssignmentSkill, HRTaskSkill, Skill, Student, StudentSkill


def _sync_student_common_skills(student):
    existing_skill_ids = set(
        StudentSkill.objects.filter(student=student).values_list("skill_id", flat=True)
    )
    missing = [
        StudentSkill(student=student, skill=skill, score=0)
        for skill in Skill.objects.all()
        if skill.id not in existing_skill_ids
    ]
    if missing:
        StudentSkill.objects.bulk_create(missing, ignore_conflicts=True)
    return len(missing)


def _sync_skill_to_students(skill):
    student_ids = list(
        Student.objects.filter(is_active=True, user__is_active=True)
        .values_list("id", flat=True)
    )
    existing_student_ids = set(
        StudentSkill.objects.filter(skill=skill, student_id__in=student_ids)
        .values_list("student_id", flat=True)
    )
    missing = [
        StudentSkill(student_id=student_id, skill=skill, score=0)
        for student_id in student_ids
        if student_id not in existing_student_ids
    ]
    if missing:
        StudentSkill.objects.bulk_create(missing, ignore_conflicts=True)
    return len(missing)


@admin_required
def admin_skills(request):
    skills = list(
        Skill.objects.annotate(
            profile_count=Count("student_profiles", distinct=True),
            assignment_count=Count("assignment_requirements", distinct=True),
            growth_task_count=Count("required_by_tasks", distinct=True),
        ).order_by("name")
    )
    active_student_count = Student.objects.filter(
        is_active=True,
        user__is_active=True,
    ).count()

    for skill in skills:
        skill.coverage_percent = (
            round((skill.profile_count / active_student_count) * 100)
            if active_student_count else 0
        )

    return render(
        request,
        "admin_ui/skills.html",
        _base_context(skills=skills, active_student_count=active_student_count),
    )


@admin_required
@require_POST
@transaction.atomic
def admin_skill_create(request):
    name = (request.POST.get("name") or "").strip()
    description = (request.POST.get("description") or "").strip()

    if not name:
        messages.error(request, "역량명을 입력해주세요.")
        return redirect("admin_skills")
    if len(name) > 80:
        messages.error(request, "역량명은 80자 이하로 입력해주세요.")
        return redirect("admin_skills")
    if len(description) > 240:
        messages.error(request, "설명은 240자 이하로 입력해주세요.")
        return redirect("admin_skills")
    if Skill.objects.filter(name__iexact=name).exists():
        messages.error(request, "같은 이름의 역량이 이미 있습니다.")
        return redirect("admin_skills")

    skill = Skill.objects.create(name=name, description=description)
    applied = _sync_skill_to_students(skill)
    messages.success(
        request,
        f"{skill.name} 역량을 만들고 활성 수강생 {applied}명에게 0점으로 적용했습니다.",
    )
    return redirect("admin_skills")


@admin_required
@require_POST
@transaction.atomic
def admin_skill_update(request, skill_id):
    skill = get_object_or_404(Skill, pk=skill_id)
    name = (request.POST.get("name") or "").strip()
    description = (request.POST.get("description") or "").strip()

    if not name:
        messages.error(request, "역량명을 입력해주세요.")
        return redirect("admin_skills")
    if len(name) > 80 or len(description) > 240:
        messages.error(request, "역량명 또는 설명 길이를 확인해주세요.")
        return redirect("admin_skills")
    if Skill.objects.filter(name__iexact=name).exclude(pk=skill.id).exists():
        messages.error(request, "같은 이름의 역량이 이미 있습니다.")
        return redirect("admin_skills")

    skill.name = name
    skill.description = description
    skill.save(update_fields=["name", "description", "updated_at"])
    applied = _sync_skill_to_students(skill)
    messages.success(
        request,
        f"{skill.name} 역량을 수정했습니다. 누락된 수강생 {applied}명도 0점으로 동기화했습니다.",
    )
    return redirect("admin_skills")


@admin_required
@require_POST
@transaction.atomic
def admin_skill_sync_all(request):
    applied = 0
    for student in Student.objects.filter(
        is_active=True,
        user__is_active=True,
    ).select_related("user"):
        applied += _sync_student_common_skills(student)

    messages.success(
        request,
        f"공통 역량 동기화를 완료했습니다. 누락된 프로필 {applied}개를 0점으로 생성했습니다.",
    )
    return redirect("admin_skills")


@admin_required
@require_POST
@transaction.atomic
def admin_skill_delete(request, skill_id):
    skill = get_object_or_404(Skill, pk=skill_id)
    assignment_count = AssignmentSkill.objects.filter(skill_id=skill.id).count()
    growth_task_count = HRTaskSkill.objects.filter(skill_id=skill.id).count()

    if assignment_count or growth_task_count:
        messages.error(
            request,
            f"{skill.name} 역량은 기본 과제 {assignment_count}개 / 추가 성장과제 {growth_task_count}개에서 사용 중이라 삭제할 수 없습니다.",
        )
        return redirect("admin_skills")

    name = skill.name
    profile_count = StudentSkill.objects.filter(skill_id=skill.id).count()
    deleted_count, _ = Skill.objects.filter(pk=skill.id).delete()

    if deleted_count <= 0 or Skill.objects.filter(pk=skill.id).exists():
        messages.error(request, f"{name} 역량 삭제에 실패했습니다. 다시 시도해주세요.")
        return redirect("admin_skills")

    messages.success(
        request,
        f"{name} 역량을 삭제했습니다. 연결된 수강생 프로필 {profile_count}개도 함께 정리했습니다.",
    )
    return redirect("admin_skills")
