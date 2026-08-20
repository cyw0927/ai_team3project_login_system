"""Admin skill dictionary and student skill profile views."""

from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .common import _base_context, _redirect_back, admin_required
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


@admin_required
@require_POST
@transaction.atomic
def admin_students_bulk_skill_save(request):
    target_mode = (request.POST.get("target_mode") or "selected").strip()
    selected_ids = [
        int(value)
        for value in request.POST.getlist("student_ids")
        if str(value).isdigit()
    ]

    if target_mode == "all_active":
        target_students = list(
            Student.objects.filter(is_active=True, user__is_active=True)
            .select_related("user")
            .order_by("user__first_name", "user__username")
        )
    else:
        target_students = list(
            Student.objects.filter(pk__in=selected_ids)
            .select_related("user")
            .order_by("user__first_name", "user__username")
        )

    if not target_students:
        messages.error(request, "역량을 적용할 수강생을 선택해주세요.")
        return _redirect_back(request, "admin_students")

    skill_ids = request.POST.getlist("skill_id")
    scores = request.POST.getlist("skill_score")
    notes = request.POST.getlist("skill_note")
    rows = []
    used_skill_ids = set()
    errors = []

    for index, raw_skill_id in enumerate(skill_ids):
        raw_skill_id = (raw_skill_id or "").strip()
        raw_score = (scores[index] if index < len(scores) else "").strip()
        note = (notes[index] if index < len(notes) else "").strip()

        if not raw_skill_id and not raw_score and not note:
            continue
        if not raw_skill_id:
            errors.append(f"{index + 1}번째 행의 역량을 선택해주세요.")
            continue
        if not raw_skill_id.isdigit():
            errors.append(f"{index + 1}번째 행의 역량값이 올바르지 않습니다.")
            continue

        skill_id = int(raw_skill_id)
        if skill_id in used_skill_ids:
            errors.append(f"{index + 1}번째 행에 같은 역량이 중복되었습니다.")
            continue
        used_skill_ids.add(skill_id)

        try:
            score = int(raw_score)
        except (TypeError, ValueError):
            errors.append(f"{index + 1}번째 행의 점수를 입력해주세요.")
            continue

        if not 0 <= score <= 100:
            errors.append(f"{index + 1}번째 행의 점수는 0~100 사이여야 합니다.")
            continue
        if len(note) > 300:
            errors.append(f"{index + 1}번째 행의 메모는 300자 이하로 입력해주세요.")
            continue

        skill = Skill.objects.filter(pk=skill_id).first()
        if not skill:
            errors.append(f"{index + 1}번째 행의 역량을 찾을 수 없습니다.")
            continue
        rows.append((skill, score, note))

    if errors:
        for error in errors[:6]:
            messages.error(request, error)
        if len(errors) > 6:
            messages.error(request, f"외 {len(errors) - 6}건의 입력 오류가 있습니다.")
        return _redirect_back(request, "admin_students")
    if not rows:
        messages.error(request, "입력할 역량을 한 개 이상 추가해주세요.")
        return _redirect_back(request, "admin_students")

    created_count = updated_count = 0
    for student in target_students:
        for skill, score, note in rows:
            _, created = StudentSkill.objects.update_or_create(
                student=student,
                skill=skill,
                defaults={"score": score, "note": note},
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

    target_label = "전체 활성 수강생" if target_mode == "all_active" else "선택 수강생"
    messages.success(
        request,
        f"{target_label} {len(target_students)}명에게 역량 {len(rows)}개를 일괄 적용했습니다. "
        f"(신규 {created_count}개 / 수정 {updated_count}개)",
    )
    return _redirect_back(request, "admin_students")
