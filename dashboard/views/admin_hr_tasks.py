from .common import *

def _task_candidate_recommendations(task, students):
    """필요 역량 가중치를 기준으로 활성 수강생의 과제 적합도를 계산한다."""
    requirements = list(task.required_skills.all())
    if not requirements:
        return []

    total_weight = sum(item.weight for item in requirements) or 0
    if total_weight <= 0:
        return []

    skill_ids = [item.skill_id for item in requirements]
    student_ids = [student.id for student in students]
    profiles = StudentSkill.objects.filter(
        student_id__in=student_ids,
        skill_id__in=skill_ids,
    ).values("student_id", "skill_id", "score")

    score_map = {
        (row["student_id"], row["skill_id"]): row["score"]
        for row in profiles
    }

    recommendations = []
    for student in students:
        weighted_sum = 0
        covered_weight = 0
        skill_breakdown = []

        for requirement in requirements:
            score = score_map.get((student.id, requirement.skill_id))
            if score is None:
                applied_score = 0
            else:
                applied_score = score
                covered_weight += requirement.weight

            weighted_sum += applied_score * requirement.weight
            skill_breakdown.append({
                "name": requirement.skill.name,
                "score": score,
                "weight": requirement.weight,
            })

        fit_score = round(weighted_sum / total_weight)
        coverage = round((covered_weight / total_weight) * 100)
        recommendations.append({
            "student": student,
            "fit_score": fit_score,
            "coverage": coverage,
            "skills": skill_breakdown,
        })

    recommendations.sort(
        key=lambda item: (
            -item["fit_score"],
            -item["coverage"],
            item["student"].name or "",
            item["student"].id,
        )
    )
    return recommendations



def _task_form_values(request):
    title = (request.POST.get("title") or "").strip()
    description = (request.POST.get("description") or "").strip()
    evaluation_round_id = (request.POST.get("evaluation_round_id") or "").strip()
    assignee_id = (request.POST.get("assignee_id") or "").strip()
    start_date = (request.POST.get("start_date") or "").strip()
    due_date = (request.POST.get("due_date") or "").strip()
    status = (request.POST.get("status") or HRTask.Status.UNASSIGNED).strip()
    priority = (request.POST.get("priority") or HRTask.Priority.NORMAL).strip()
    skill_ids = request.POST.getlist("skill_id")
    weights = request.POST.getlist("skill_weight")
    return title, description, evaluation_round_id, assignee_id, start_date, due_date, status, priority, skill_ids, weights


def _validate_task_payload(title, start_date, due_date, status, priority, skill_ids, weights):
    errors = []
    if not title:
        errors.append("과제명을 입력해주세요.")
    if len(title) > 160:
        errors.append("과제명은 160자 이하로 입력해주세요.")
    if status not in HRTask.Status.values:
        errors.append("유효하지 않은 상태값입니다.")
    if priority not in HRTask.Priority.values:
        errors.append("유효하지 않은 우선순위입니다.")
    if start_date and due_date and due_date < start_date:
        errors.append("마감일은 시작일보다 빠를 수 없습니다.")

    parsed_skills = []
    used_skill_ids = set()
    for raw_skill_id, raw_weight in zip(skill_ids, weights):
        raw_skill_id = (raw_skill_id or "").strip()
        raw_weight = (raw_weight or "").strip()
        if not raw_skill_id:
            continue
        try:
            skill_id = int(raw_skill_id)
            weight = int(raw_weight)
        except (TypeError, ValueError):
            errors.append("필요 역량과 중요도 값을 확인해주세요.")
            continue
        if skill_id in used_skill_ids:
            errors.append("같은 Skill을 두 번 설정할 수 없습니다.")
            continue
        if not 1 <= weight <= 100:
            errors.append("Skill 중요도는 1~100 사이여야 합니다.")
            continue
        used_skill_ids.add(skill_id)
        parsed_skills.append((skill_id, weight))

    if parsed_skills and sum(weight for _, weight in parsed_skills) != 100:
        errors.append("필요 역량 중요도의 합계는 100%여야 합니다.")

    return errors, parsed_skills


def _save_task_skills(task, parsed_skills):
    task.required_skills.all().delete()
    skill_map = {
        skill.id: skill
        for skill in Skill.objects.filter(id__in=[skill_id for skill_id, _ in parsed_skills])
    }
    for skill_id, weight in parsed_skills:
        skill = skill_map.get(skill_id)
        if skill:
            HRTaskSkill.objects.create(task=task, skill=skill, weight=weight)


@admin_required
def admin_hr_tasks(request):
    query = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()

    tasks = (
        HRTask.objects.select_related("assignee__user", "evaluation_round")
        .prefetch_related("required_skills__skill", "steps")
    )
    if query:
        tasks = tasks.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(assignee__user__first_name__icontains=query)
            | Q(assignee__user__last_name__icontains=query)
            | Q(required_skills__skill__name__icontains=query)
        ).distinct()
    if status_filter in HRTask.Status.values:
        tasks = tasks.filter(status=status_filter)

    students = list(
        Student.objects.filter(is_active=True)
        .select_related("user")
        .order_by("user__first_name", "user__username")
    )

    tasks = list(tasks)
    for task in tasks:
        task.skill_items = list(task.required_skills.all())
        task.skill_weight_total = sum(item.weight for item in task.skill_items)
        task.step_items = list(task.steps.all())
        task.submission_obj = HRTaskSubmission.objects.filter(task=task).select_related("student__user").first()
        task.evaluation_obj = HRTaskEvaluation.objects.filter(task=task).select_related("evaluated_by").first()
        task.skill_update_items = list(
            HRTaskSkillUpdate.objects.filter(task=task).select_related("skill").order_by("skill__name")
        )
        task.recommendations = _task_candidate_recommendations(task, students)[:3]
        task.best_recommendation = task.recommendations[0] if task.recommendations else None

    stats = {
        "total": HRTask.objects.count(),
        "active": HRTask.objects.filter(status=HRTask.Status.IN_PROGRESS).count(),
        "review": HRTask.objects.filter(status=HRTask.Status.REVIEW).count(),
        "overdue": sum(
            1
            for task in HRTask.objects.exclude(status=HRTask.Status.COMPLETED)
            if task.is_overdue
        ),
    }

    return render(
        request,
        "admin_ui/hr_tasks.html",
        _base_context(
            tasks=tasks,
            students=students,
            skills=Skill.objects.all(),
            evaluation_rounds=EvaluationRound.objects.order_by("-start_at"),
            status_choices=HRTask.Status.choices,
            priority_choices=HRTask.Priority.choices,
            status_filter=status_filter,
            query=query,
            task_stats=stats,
        ),
    )


@admin_required
@require_POST
@transaction.atomic
def admin_hr_task_save(request, task_id=None):
    task = get_object_or_404(HRTask, pk=task_id) if task_id else HRTask(created_by=request.user)
    (
        title, description, evaluation_round_id, assignee_id, start_date, due_date,
        status, priority, skill_ids, weights,
    ) = _task_form_values(request)

    errors, parsed_skills = _validate_task_payload(
        title, start_date, due_date, status, priority, skill_ids, weights
    )

    evaluation_round = None
    if evaluation_round_id:
        try:
            evaluation_round = EvaluationRound.objects.get(pk=int(evaluation_round_id))
        except (EvaluationRound.DoesNotExist, TypeError, ValueError):
            errors.append("선택한 평가 회차를 찾을 수 없습니다.")

    assignee = None
    if assignee_id:
        try:
            assignee = Student.objects.get(pk=int(assignee_id), is_active=True)
        except (Student.DoesNotExist, TypeError, ValueError):
            errors.append("선택한 담당자를 찾을 수 없습니다.")

    selected_skill_ids = [skill_id for skill_id, _ in parsed_skills]
    if selected_skill_ids and Skill.objects.filter(id__in=selected_skill_ids).count() != len(selected_skill_ids):
        errors.append("존재하지 않는 Skill이 포함되어 있습니다.")

    if errors:
        for error in errors:
            messages.error(request, error)
        return _redirect_back(request, "admin_hr_tasks")

    task.title = title
    task.description = description
    uploaded_attachment = request.FILES.get("attachment")
    if uploaded_attachment:
        task.attachment = uploaded_attachment
    task.evaluation_round = evaluation_round
    task.assignee = assignee
    task.start_date = start_date or None
    task.due_date = due_date or None
    task.status = status
    task.priority = priority
    task.full_clean()
    task.save()

    _save_task_skills(task, parsed_skills)
    messages.success(request, f"{task.title} 과제를 저장했습니다.")
    return redirect("admin_hr_tasks")


@admin_required
@require_POST
@transaction.atomic
def admin_hr_task_delete(request, task_id):
    """역량 과제와 연결 데이터를 실제 삭제하고, 반영된 역량점수도 되돌린다."""
    task = get_object_or_404(
        HRTask.objects.select_related("assignee")
        .prefetch_related("skill_updates__skill"),
        pk=task_id,
    )
    title = task.title

    # 이 과제 평가로 역량에 반영했던 변화량을 현재 점수에서 제거한다.
    # 이후 다른 과제로 올라간 점수는 보존하고, 이 과제 기여분만 되돌린다.
    reverted_count = 0
    for update in list(task.skill_updates.all()):
        profile = StudentSkill.objects.filter(
            student=update.student,
            skill=update.skill,
        ).first()
        if not profile:
            continue
        delta = update.new_score - update.previous_score
        reverted_score = max(0, min(100, profile.score - delta))
        if profile.score != reverted_score:
            profile.score = reverted_score
            profile.note = (
                f"{profile.note} / " if profile.note else ""
            ) + f"삭제된 역량 과제 '{title}' 반영분 취소"
            profile.note = profile.note[-300:]
            profile.save(update_fields=["score", "note", "updated_at"])
            reverted_count += 1

    # DB 삭제 후에도 실제 파일이 media 폴더에 남지 않도록 경로를 먼저 기억한다.
    task_attachment = task.attachment.name if getattr(task, "attachment", None) else ""
    submission = HRTaskSubmission.objects.filter(task=task).first()
    submission_attachment = (
        submission.attachment.name
        if submission and submission.attachment
        else ""
    )

    # CASCADE 관계: Step, 필요역량, 제출, 평가, 역량반영 이력이 함께 삭제된다.
    task.delete()

    # DB transaction 성공 시에만 실제 저장 파일을 제거한다.
    def _delete_files():
        from django.core.files.storage import default_storage
        for name in {task_attachment, submission_attachment}:
            if not name:
                continue
            try:
                if default_storage.exists(name):
                    default_storage.delete(name)
            except OSError:
                pass

    transaction.on_commit(_delete_files)

    messages.success(
        request,
        f"{title} 과제를 삭제했습니다. 연결 데이터와 파일을 정리하고 역량 반영 {reverted_count}건을 취소했습니다.",
    )
    return redirect("admin_hr_tasks")


@admin_required
@require_POST
@transaction.atomic
def admin_hr_task_step_add(request, task_id):
    task = get_object_or_404(HRTask, pk=task_id)
    title = (request.POST.get("step_title") or "").strip()
    detail = (request.POST.get("step_detail") or "").strip()
    if not title:
        messages.error(request, "Step 이름을 입력해주세요.")
        return _redirect_back(request, "admin_hr_tasks")
    if len(title) > 160:
        messages.error(request, "Step 이름은 160자 이하로 입력해주세요.")
        return _redirect_back(request, "admin_hr_tasks")
    if len(detail) > 3000:
        messages.error(request, "Step 상세 지시사항은 3000자 이하로 입력해주세요.")
        return _redirect_back(request, "admin_hr_tasks")

    next_order = (task.steps.order_by("-order").values_list("order", flat=True).first() or 0) + 1
    HRTaskStep.objects.create(task=task, title=title, detail=detail, order=next_order)
    messages.success(request, f"{task.title}에 Step을 추가했습니다.")
    return _redirect_back(request, "admin_hr_tasks")


@admin_required
@require_POST
@transaction.atomic
def admin_hr_task_step_update(request, task_id, step_id):
    task = get_object_or_404(HRTask, pk=task_id)
    step = get_object_or_404(HRTaskStep, pk=step_id, task=task)
    title = (request.POST.get("step_title") or "").strip()
    detail = (request.POST.get("step_detail") or "").strip()

    if not title:
        messages.error(request, "Step 이름을 입력해주세요.")
        return _redirect_back(request, "admin_hr_tasks")
    if len(title) > 160:
        messages.error(request, "Step 이름은 160자 이하로 입력해주세요.")
        return _redirect_back(request, "admin_hr_tasks")
    if len(detail) > 3000:
        messages.error(request, "Step 상세 지시사항은 3000자 이하로 입력해주세요.")
        return _redirect_back(request, "admin_hr_tasks")

    step.title = title
    step.detail = detail
    step.save(update_fields=["title", "detail", "updated_at"])
    messages.success(request, "Step 내용을 수정했습니다.")
    return _redirect_back(request, "admin_hr_tasks")


@admin_required
@require_POST
@transaction.atomic
def admin_hr_task_step_delete(request, task_id, step_id):
    task = get_object_or_404(HRTask, pk=task_id)
    step = get_object_or_404(HRTaskStep, pk=step_id, task=task)
    step.delete()

    # 순서를 1부터 다시 정돈한다.
    for order, item in enumerate(task.steps.order_by("order", "id"), start=1):
        if item.order != order:
            HRTaskStep.objects.filter(pk=item.pk).update(order=order)

    messages.success(request, "Step을 삭제했습니다.")
    return _redirect_back(request, "admin_hr_tasks")


@admin_required
@require_POST
@transaction.atomic
def admin_hr_task_request_revision(request, task_id):
    """검토 중인 과제를 수강생에게 수정 요청으로 돌려보낸다."""
    task = get_object_or_404(HRTask, pk=task_id)
    if not hasattr(task, "submission"):
        messages.error(request, "제출 기록이 없어 수정 요청을 보낼 수 없습니다.")
        return redirect("admin_hr_tasks")

    task.status = HRTask.Status.IN_PROGRESS
    task.save(update_fields=["status", "updated_at"])
    messages.success(request, f"{task.title} 과제를 수정 요청 상태로 되돌렸습니다.")
    return redirect("admin_hr_tasks")


@admin_required
@require_POST
@transaction.atomic
def admin_hr_task_evaluate(request, task_id):
    """제출물을 평가하고 과제의 필요 역량을 수강생 역량 프로필에 반영한다."""
    task = get_object_or_404(
        HRTask.objects.select_related("assignee").prefetch_related("required_skills__skill"),
        pk=task_id,
    )
    if task.status != HRTask.Status.REVIEW:
        messages.error(request, "검토 요청 상태의 과제만 평가할 수 있습니다.")
        return redirect("admin_hr_tasks")
    if not task.assignee:
        messages.error(request, "담당자가 없는 과제는 평가할 수 없습니다.")
        return redirect("admin_hr_tasks")

    submission = HRTaskSubmission.objects.filter(task=task).first()
    if not submission:
        messages.error(request, "제출물이 없는 과제는 평가할 수 없습니다.")
        return redirect("admin_hr_tasks")

    raw_score = (request.POST.get("score") or "").strip()
    comment = (request.POST.get("comment") or "").strip()
    try:
        score = int(raw_score)
    except (TypeError, ValueError):
        score = -1

    if not 0 <= score <= 100:
        messages.error(request, "평가 점수는 0~100 사이로 입력해주세요.")
        return redirect("admin_hr_tasks")
    if len(comment) > 3000:
        messages.error(request, "평가 코멘트는 3000자 이하로 입력해주세요.")
        return redirect("admin_hr_tasks")

    HRTaskEvaluation.objects.update_or_create(
        task=task,
        defaults={
            "student": task.assignee,
            "score": score,
            "comment": comment,
            "evaluated_by": request.user,
            "evaluated_at": timezone.now(),
        },
    )

    # Skill 업데이트 공식:
    # 새 점수 = 기존 점수 + (과제평가 - 기존 점수) × (Skill 중요도 / 100) × 0.30
    # 기존 Profile이 없으면 중립값 50점에서 시작한다.
    updated_skill_names = []
    for requirement in task.required_skills.select_related("skill").all():
        profile, _ = StudentSkill.objects.get_or_create(
            student=task.assignee,
            skill=requirement.skill,
            defaults={"score": 0, "note": "역량 과제 평가로 자동 생성"},
        )
        previous_score = profile.score
        influence = (requirement.weight / 100) * 0.30
        new_score = round(previous_score + (score - previous_score) * influence)
        new_score = max(0, min(100, new_score))

        profile.score = new_score
        profile.save(update_fields=["score", "updated_at"])

        HRTaskSkillUpdate.objects.create(
            task=task,
            student=task.assignee,
            skill=requirement.skill,
            previous_score=previous_score,
            new_score=new_score,
            task_score=score,
            skill_weight=requirement.weight,
        )
        updated_skill_names.append(
            f"{requirement.skill.name} {previous_score}→{new_score}"
        )

    task.status = HRTask.Status.COMPLETED
    task.save(update_fields=["status", "updated_at"])

    # 연결된 평가 회차가 있으면 과제 성과가 즉시 배지 산정에 반영되도록 재계산한다.
    if task.evaluation_round_id:
        _recalculate_round_results(task.evaluation_round)

    if updated_skill_names:
        messages.success(
            request,
            f"{task.title} 평가 완료 · Skill 업데이트: " + ", ".join(updated_skill_names),
        )
    else:
        messages.success(
            request,
            f"{task.title} 평가를 저장하고 완료 처리했습니다. 설정된 필요 역량이 없어 역량 점수는 변경되지 않았습니다.",
        )
    return redirect("admin_hr_tasks")


@admin_required
@require_POST
@transaction.atomic
def admin_hr_task_assign_recommended(request, task_id, student_id):
    """추천 목록에서 선택한 활성 학생을 과제 담당자로 확정한다."""
    task = get_object_or_404(HRTask, pk=task_id)
    student = get_object_or_404(Student.objects.select_related("user"), pk=student_id, is_active=True)

    requirements = list(task.required_skills.select_related("skill").all())
    if not requirements:
        messages.error(request, "필요 역량이 설정되지 않아 추천 배정을 사용할 수 없습니다.")
        return redirect("admin_hr_tasks")

    task.assignee = student
    if task.status == HRTask.Status.UNASSIGNED:
        task.status = HRTask.Status.SCHEDULED
        task.save(update_fields=["assignee", "status", "updated_at"])
    else:
        task.save(update_fields=["assignee", "updated_at"])

    recommendations = _task_candidate_recommendations(task, [student])
    fit_score = recommendations[0]["fit_score"] if recommendations else 0
    messages.success(
        request,
        f"{student.name}님을 {task.title} 담당자로 배정했습니다. 현재 역량 적합도는 {fit_score}%입니다.",
    )
    return redirect("admin_hr_tasks")
