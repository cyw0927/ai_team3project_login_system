from .common import *


@admin_required
def admin_hr_dashboard(request):
    """수강생 역량 과제와 역량 현황을 한 화면에서 요약한다."""
    tasks = list(
        HRTask.objects.select_related("assignee__user")
        .prefetch_related("steps", "required_skills__skill")
        .order_by("due_date", "-created_at")
    )
    students = list(
        Student.objects.filter(is_active=True)
        .select_related("user")
        .order_by("user__first_name", "user__username")
    )

    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == HRTask.Status.COMPLETED)
    in_progress = sum(1 for t in tasks if t.status == HRTask.Status.IN_PROGRESS)
    review = sum(1 for t in tasks if t.status == HRTask.Status.REVIEW)
    overdue = sum(1 for t in tasks if t.is_overdue)
    avg_progress = round(sum(t.progress_percent for t in tasks) / total) if total else 0

    overdue_tasks = [t for t in tasks if t.is_overdue][:8]
    review_tasks = [t for t in tasks if t.status == HRTask.Status.REVIEW][:8]
    active_tasks = [
        t for t in tasks
        if t.status in {HRTask.Status.SCHEDULED, HRTask.Status.IN_PROGRESS}
    ][:8]

    # 수강생별 역량 평균과 배정 과제 수
    skill_rows = StudentSkill.objects.filter(student__in=students).values(
        "student_id"
    ).annotate(
        skill_count=Count("id"),
        avg_skill=Avg("score"),
    )
    skill_map = {row["student_id"]: row for row in skill_rows}
    task_counts = (
        HRTask.objects.filter(assignee__in=students)
        .exclude(status=HRTask.Status.COMPLETED)
        .values("assignee_id")
        .annotate(active_task_count=Count("id"))
    )
    task_count_map = {row["assignee_id"]: row["active_task_count"] for row in task_counts}

    people = []
    for student in students:
        skill = skill_map.get(student.id, {})
        people.append({
            "student": student,
            "avg_skill": round(float(skill.get("avg_skill") or 0)),
            "skill_count": skill.get("skill_count") or 0,
            "active_task_count": task_count_map.get(student.id, 0),
        })
    people.sort(key=lambda row: (-row["avg_skill"], row["student"].name or ""))

    recent_evaluations = list(
        HRTaskEvaluation.objects.select_related("task", "student__user")
        .order_by("-evaluated_at")[:8]
    )
    avg_task_score = round(
        float(
            HRTaskEvaluation.objects.aggregate(avg=Avg("score"))["avg"] or 0
        ),
        1,
    )

    return render(
        request,
        "admin_ui/hr_dashboard.html",
        _base_context(
            summary={
                "total": total,
                "completed": completed,
                "in_progress": in_progress,
                "review": review,
                "overdue": overdue,
                "avg_progress": avg_progress,
                "avg_task_score": avg_task_score,
            },
            overdue_tasks=overdue_tasks,
            review_tasks=review_tasks,
            active_tasks=active_tasks,
            people=people[:10],
            recent_evaluations=recent_evaluations,
        ),
    )
