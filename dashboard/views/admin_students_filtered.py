"""Enhanced student list filters for evaluation completion status."""

from .common import *


@admin_required
def admin_students(request):
    query = request.GET.get("q", "").strip()
    team_filter = request.GET.get("team", "").strip()
    eval_status_filter = request.GET.get("eval_status", "").strip()
    if eval_status_filter not in {"", "complete", "missing"}:
        eval_status_filter = ""

    current_round = _current_round()
    teams = _round_teams(current_round)

    students_qs = Student.objects.select_related("user").order_by(
        "user__first_name", "user__username"
    )
    if current_round and team_filter:
        if team_filter == "unassigned":
            students_qs = students_qs.exclude(
                team_memberships__team__evaluation_round=current_round
            )
        elif team_filter.isdigit():
            students_qs = students_qs.filter(
                team_memberships__team__evaluation_round=current_round,
                team_memberships__team_id=int(team_filter),
            )

    if query:
        students_qs = students_qs.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__email__icontains=query)
            | Q(user__username__icontains=query)
            | Q(affiliation__icontains=query)
        )

    students = list(students_qs.distinct())

    membership_map = {}
    if current_round and students:
        memberships = (
            TeamMembership.objects.filter(
                student_id__in=[student.id for student in students],
                team__evaluation_round=current_round,
            )
            .select_related("team")
            .order_by("team__name")
        )
        membership_map = {membership.student_id: membership.team for membership in memberships}

    badge_map = {}
    if students:
        badge_rows = (
            StudentBadge.objects.filter(student_id__in=[student.id for student in students])
            .select_related("evaluation_round")
            .order_by("student_id", "-evaluation_round__start_at", "badge_type")
        )
        grouped = {}
        for badge in badge_rows:
            grouped.setdefault(badge.student_id, []).append(badge)
        for student_id, badges in grouped.items():
            by_type = {}
            for badge in badges:
                item = by_type.setdefault(
                    badge.badge_type,
                    {
                        "type": badge.badge_type,
                        "label": badge.get_badge_type_display(),
                        "count": 0,
                        "round_names": [],
                    },
                )
                item["count"] += 1
                item["round_names"].append(badge.evaluation_round.name)
            badge_map[student_id] = list(by_type.values())

    missing_student_count = 0
    completed_student_count = 0
    for student in students:
        student.current_team = membership_map.get(student.id)
        student.badge_summary = badge_map.get(student.id, [])
        student.evaluation_missing_count = 0
        student.has_missing_evaluation = False
        student.evaluation_complete = False

        eligible = bool(
            current_round
            and student.current_team
            and student.is_active
            and student.user.is_active
        )
        if eligible:
            progress = _student_progress(student, current_round, student.current_team)
            required_total = progress["team_total"] + progress["personal_total"]
            completed_total = progress["team_completed"] + progress["personal_completed"]
            student.evaluation_missing_count = max(required_total - completed_total, 0)
            student.has_missing_evaluation = student.evaluation_missing_count > 0
            student.evaluation_complete = (
                required_total > 0 and student.evaluation_missing_count == 0
            )
            if student.has_missing_evaluation:
                missing_student_count += 1
            elif student.evaluation_complete:
                completed_student_count += 1

    if eval_status_filter == "complete":
        students = [student for student in students if student.evaluation_complete]
    elif eval_status_filter == "missing":
        students = [student for student in students if student.has_missing_evaluation]

    paginator = Paginator(students, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    students = list(page_obj.object_list)

    all_students = Student.objects.all()
    stats = {
        "total": all_students.count(),
        "active": all_students.filter(is_active=True, user__is_active=True).count(),
        "inactive": all_students.filter(
            Q(is_active=False) | Q(user__is_active=False)
        ).distinct().count(),
        "unassigned": (
            all_students.exclude(
                team_memberships__team__evaluation_round=current_round
            ).count()
            if current_round
            else all_students.count()
        ),
    }

    return render(
        request,
        "admin_ui/students.html",
        _base_context(
            students=students,
            page_obj=page_obj,
            teams=teams,
            current_round=current_round,
            query=query,
            team_filter=team_filter,
            eval_status_filter=eval_status_filter,
            stats=stats,
            missing_student_count=missing_student_count,
            completed_student_count=completed_student_count,
            skills=Skill.objects.all().order_by("name"),
        ),
    )
