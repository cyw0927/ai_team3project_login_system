from .common import *

@admin_required
def admin_dashboard(request):
    _sync_round_statuses()
    current_round = _current_round()
    student_count = Student.objects.filter(is_active=True).count()
    active_team_count = 0
    team_submission_count = 0
    personal_submission_count = 0
    team_required = 0
    personal_required = 0

    if current_round:
        current_round.status_display = current_round.get_status_display()
        active_teams = list(Team.objects.filter(evaluation_round=current_round, is_active=True))
        active_team_count = len(active_teams)
        memberships = list(
            TeamMembership.objects.filter(team__evaluation_round=current_round, team__is_active=True)
            .select_related("team", "student")
        )
        member_count_by_team = {}
        for membership in memberships:
            member_count_by_team[membership.team_id] = member_count_by_team.get(membership.team_id, 0) + 1

        # 배정된 활성 수강생 기준 필요한 제출 건수 계산
        # 발표 당일 결석/공결 학생은 팀평가 의무에서 제외하고,
        # 같은 팀원 개인평가는 기존 정책대로 유지한다.
        attendance_map = dict(
            RoundAttendance.objects.filter(
                evaluation_round=current_round,
                student_id__in=[m.student_id for m in memberships],
            ).values_list("student_id", "status")
        )
        for membership in memberships:
            if not membership.student.is_active:
                continue
            attendance_status = attendance_map.get(membership.student_id, RoundAttendance.Status.PRESENT)
            if attendance_status == RoundAttendance.Status.PRESENT:
                team_required += max(active_team_count - 1, 0)
            personal_required += max(member_count_by_team.get(membership.team_id, 0) - 1, 0)

        team_submission_count = TeamEvaluation.objects.filter(
            evaluation_round=current_round, evaluator__is_active=True, is_submitted=True
        ).count()
        personal_submission_count = PersonalEvaluation.objects.filter(
            evaluation_round=current_round, evaluator__is_active=True, is_submitted=True
        ).count()

    required_total = team_required + personal_required
    submitted_total = min(team_submission_count, team_required) + min(personal_submission_count, personal_required)
    overall_percent = round((submitted_total / required_total) * 100) if required_total else 0
    missing_submission_count = max(required_total - submitted_total, 0)

    # 관리자 홈에서 바로 운영 판단을 할 수 있도록 회차/과제 요약도 함께 계산한다.
    now = timezone.now()
    assignment_count = Assignment.objects.count()
    attachment_count = Assignment.objects.exclude(attachment="").count()
    in_progress_round_count = EvaluationRound.objects.filter(
        status=EvaluationRound.Status.IN_PROGRESS
    ).count()
    ending_soon_count = EvaluationRound.objects.filter(
        status=EvaluationRound.Status.IN_PROGRESS,
        end_at__gte=now,
        end_at__lte=now + timedelta(days=2),
    ).count()

    recent_assignments = list(
        Assignment.objects.select_related("evaluation_round")
        .order_by("-evaluation_round__start_at", "-created_at")[:5]
    )
    for assignment in recent_assignments:
        round_obj = assignment.evaluation_round
        assignment.round_status = round_obj.get_status_display()
        assignment.is_current = bool(current_round and round_obj.pk == current_round.pk)
        assignment.has_attachment = bool(assignment.attachment)

    current_assignment = None
    workflow_steps = []
    if current_round:
        current_assignment = Assignment.objects.filter(
            evaluation_round=current_round
        ).select_related("evaluation_round").first()

        has_teams = Team.objects.filter(evaluation_round=current_round, is_active=True).exists()
        has_assignment = Assignment.objects.filter(evaluation_round=current_round).exists()
        has_team_template = EvaluationTemplate.objects.filter(
            evaluation_round=current_round,
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
            is_active=True,
        ).exists()
        has_personal_template = EvaluationTemplate.objects.filter(
            evaluation_round=current_round,
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
            is_active=True,
        ).exists()
        templates_ready = has_team_template and has_personal_template
        publish_setting = ResultPublishSetting.objects.filter(evaluation_round=current_round).first()
        is_published = bool(publish_setting and (
            publish_setting.is_published or
            (publish_setting.publish_at and publish_setting.publish_at <= timezone.now())
        ))

        workflow_steps = [
            {"number": 1, "label": "회차", "detail": "운영 회차 생성", "done": True, "url_name": "admin_rounds"},
            {"number": 2, "label": "팀 편성", "detail": "학생 팀 배정", "done": has_teams, "url_name": "admin_team_assignment"},
            {"number": 3, "label": "과제", "detail": "개별/조별 과제 등록", "done": has_assignment, "url_name": "admin_assignments"},
            {"number": 4, "label": "평가 템플릿", "detail": "팀/개인 템플릿 적용", "done": templates_ready, "url_name": "admin_evaluation_templates"},
            {"number": 5, "label": "평가 시작", "detail": "평가 진행 상태 전환", "done": current_round.evaluation_started, "url_name": "admin_operations"},
            {"number": 6, "label": "결과 공개", "detail": "점수 확인 후 학생 공개", "done": is_published, "url_name": "admin_result_settings"},
        ]

        first_pending_found = False
        for step in workflow_steps:
            step["current"] = False
            if not first_pending_found and not step["done"]:
                step["current"] = True
                first_pending_found = True

    # 관리자 홈 경고 센터: 지금 처리해야 할 일만 간단히 노출한다.
    admin_alerts = []
    if current_round:
        if current_round.status == EvaluationRound.Status.IN_PROGRESS:
            remaining = current_round.end_at - now
            if remaining.total_seconds() >= 0 and remaining <= timedelta(days=1):
                hours_left = max(0, int(remaining.total_seconds() // 3600))
                admin_alerts.append({
                    "level": "danger" if hours_left <= 6 else "warning",
                    "icon": "bi-alarm",
                    "title": f"평가 마감 {hours_left}시간 전",
                    "detail": f"{current_round.name} 마감이 임박했습니다.",
                    "url_name": "admin_operations",
                    "action": "운영 확인",
                })
        if missing_submission_count > 0 and current_round.evaluation_started:
            admin_alerts.append({
                "level": "warning",
                "icon": "bi-person-exclamation",
                "title": f"미제출 평가 {missing_submission_count}건",
                "detail": "아직 제출되지 않은 평가가 있습니다.",
                "url_name": "admin_missing_evaluations",
                "action": "미제출 확인",
            })
        if not has_teams:
            admin_alerts.append({
                "level": "info", "icon": "bi-diagram-3", "title": "팀 편성이 필요합니다.",
                "detail": "현재 회차에 활성 팀이 없습니다.", "url_name": "admin_team_assignment", "action": "팀 편성",
            })
        if not has_assignment:
            admin_alerts.append({
                "level": "info", "icon": "bi-folder-plus", "title": "과제가 등록되지 않았습니다.",
                "detail": "평가 시작 전에 과제를 등록해 주세요.", "url_name": "admin_assignments", "action": "과제 등록",
            })
        if not templates_ready:
            admin_alerts.append({
                "level": "info", "icon": "bi-ui-checks-grid", "title": "평가 템플릿이 준비되지 않았습니다.",
                "detail": "팀 평가와 개인 평가 템플릿을 모두 적용해 주세요.", "url_name": "admin_evaluation_templates", "action": "템플릿 확인",
            })
        if current_round.status == EvaluationRound.Status.ENDED and not is_published:
            admin_alerts.append({
                "level": "warning", "icon": "bi-eye-slash", "title": "결과가 아직 공개되지 않았습니다.",
                "detail": "점수를 확인한 뒤 학생 공개 여부를 설정해 주세요.", "url_name": "admin_result_settings", "action": "공개 설정",
            })

    # 관리자 홈 역량과제 요약
    growth_tasks = list(
        HRTask.objects.select_related("assignee__user")
        .exclude(status=HRTask.Status.COMPLETED)
        .order_by("due_date", "-updated_at")
    )
    growth_task_summary = {
        "active": sum(1 for task in growth_tasks if task.status == HRTask.Status.IN_PROGRESS),
        "review": sum(1 for task in growth_tasks if task.status == HRTask.Status.REVIEW),
        "overdue": sum(1 for task in growth_tasks if task.is_overdue),
        "scheduled": sum(1 for task in growth_tasks if task.status == HRTask.Status.SCHEDULED),
    }
    growth_attention_tasks = sorted(
        [
            task for task in growth_tasks
            if task.status == HRTask.Status.REVIEW or task.is_overdue
        ],
        key=lambda task: (
            0 if task.status == HRTask.Status.REVIEW else 1,
            task.due_date or timezone.localdate(),
            task.id,
        ),
    )[:5]

    stats = {
        "student_count": student_count,
        "active_team_count": active_team_count,
        "team_submission_count": team_submission_count,
        "team_required": team_required,
        "personal_submission_count": personal_submission_count,
        "personal_required": personal_required,
        "missing_submission_count": missing_submission_count,
        "overall_percent": overall_percent,
        "assignment_count": assignment_count,
        "attachment_count": attachment_count,
        "in_progress_round_count": in_progress_round_count,
        "ending_soon_count": ending_soon_count,
    }
    return render(
        request,
        "admin_ui/dashboard.html",
        _base_context(
            current_round=current_round,
            current_assignment=current_assignment,
            recent_assignments=recent_assignments,
            workflow_steps=workflow_steps,
            admin_alerts=admin_alerts,
            growth_task_summary=growth_task_summary,
            growth_attention_tasks=growth_attention_tasks,
            stats=stats,
        ),
    )

@admin_required
def admin_operations(request):
    """과제와 평가 회차를 한 화면에서 운영하는 통합 관리 화면."""
    _sync_round_statuses()
    rounds = list(
        EvaluationRound.objects.all()
        .prefetch_related("teams", "evaluation_templates")
        .order_by("-start_at")
    )
    now = timezone.now()
    for evaluation_round in rounds:
        assignment = evaluation_round.assignments.first()
        evaluation_round.status_display = evaluation_round.get_status_display()
        evaluation_round.assignment_obj = assignment
        evaluation_round.assignment_title = assignment.title if assignment else ""
        evaluation_round.team_count = evaluation_round.teams.filter(is_active=True).count()
        evaluation_round.template_count = evaluation_round.evaluation_templates.filter(is_active=True).count()
        evaluation_round.team_template_count = evaluation_round.evaluation_templates.filter(
            is_active=True, evaluation_type=EvaluationTemplate.EvaluationType.TEAM
        ).count()
        evaluation_round.personal_template_count = evaluation_round.evaluation_templates.filter(
            is_active=True, evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL
        ).count()
        evaluation_round.can_edit = evaluation_round.status == EvaluationRound.Status.SCHEDULED
        evaluation_round.can_round_start = evaluation_round.status == EvaluationRound.Status.SCHEDULED
        evaluation_round.can_evaluation_start = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and not evaluation_round.evaluation_started
        evaluation_round.can_end = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started
        evaluation_round.can_reopen = evaluation_round.status == EvaluationRound.Status.ENDED
        evaluation_round.can_lock = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started and not evaluation_round.is_locked
        evaluation_round.can_unlock = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started and evaluation_round.is_locked
        evaluation_round.ready_checks = {
            "assignment": bool(assignment),
            "teams": evaluation_round.team_count > 0,
            "team_template": evaluation_round.team_template_count > 0,
            "personal_template": evaluation_round.personal_template_count > 0,
        }
        evaluation_round.ready_count = sum(evaluation_round.ready_checks.values())
        evaluation_round.ready_percent = int(evaluation_round.ready_count / 4 * 100)
        if evaluation_round.status == EvaluationRound.Status.SCHEDULED:
            evaluation_round.time_label = "시작 전 · 과제 등록 가능"
        elif evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and not evaluation_round.evaluation_started:
            evaluation_round.time_label = "진행 중 · 평가 시작 전"
        elif evaluation_round.status == EvaluationRound.Status.IN_PROGRESS:
            delta = evaluation_round.end_at - now
            hours = max(0, int(delta.total_seconds() // 3600))
            evaluation_round.time_label = f"평가 중 · 마감 {hours}시간 전" if hours < 48 else f"평가 중 · 마감 {max(0, delta.days)}일 전"
        else:
            evaluation_round.time_label = "종료됨"

    available_rounds = EvaluationRound.objects.filter(
        Q(status=EvaluationRound.Status.SCHEDULED) | Q(status=EvaluationRound.Status.IN_PROGRESS, evaluation_started=False)
    ).order_by("-start_at")
    stats = {
        "total": len(rounds),
        "active": sum(r.status == EvaluationRound.Status.IN_PROGRESS for r in rounds),
        "ready": sum(r.ready_count == 4 for r in rounds if r.status in {EvaluationRound.Status.SCHEDULED, EvaluationRound.Status.IN_PROGRESS} and not r.evaluation_started),
        "missing_assignment": sum(not r.assignment_obj for r in rounds),
    }
    selected_round = None
    selected_id = request.GET.get("round", "").strip()
    if selected_id.isdigit():
        selected_round = next((r for r in rounds if r.id == int(selected_id)), None)
    if selected_round is None:
        selected_round = next((r for r in rounds if r.status == EvaluationRound.Status.IN_PROGRESS), None) or (rounds[0] if rounds else None)

    return render(
        request,
        "admin_ui/operations.html",
        _base_context(
            rounds=rounds,
            selected_round=selected_round,
            available_rounds=available_rounds,
            stats=stats,
        ),
    )

@admin_required
def admin_attendance(request):
    """회차별 발표 당일 출결과 평가 권한을 관리한다."""
    _sync_round_statuses()
    rounds = list(EvaluationRound.objects.all().order_by("-start_at"))
    selected_id = request.GET.get("round", "").strip()
    selected_round = None
    if selected_id.isdigit():
        selected_round = next((r for r in rounds if r.id == int(selected_id)), None)
    if selected_round is None:
        selected_round = next((r for r in rounds if r.status == EvaluationRound.Status.IN_PROGRESS), None) or (rounds[0] if rounds else None)

    if request.method == "POST":
        round_id = request.POST.get("round_id", "").strip()
        evaluation_round = get_object_or_404(EvaluationRound, pk=round_id)
        action = request.POST.get("action", "save")
        students = list(Student.objects.filter(is_active=True, user__is_active=True).select_related("user").order_by("user__first_name", "user__username"))
        if action == "mark_all_present":
            for student in students:
                RoundAttendance.objects.update_or_create(
                    evaluation_round=evaluation_round, student=student,
                    defaults={"status": RoundAttendance.Status.PRESENT, "note": ""},
                )
            messages.success(request, f"{evaluation_round.name} 전체 학생을 출석으로 처리했습니다.")
        else:
            valid_statuses = set(RoundAttendance.Status.values)
            updated = 0
            for student in students:
                status = request.POST.get(f"status_{student.id}", RoundAttendance.Status.PRESENT)
                if status not in valid_statuses:
                    status = RoundAttendance.Status.PRESENT
                note = request.POST.get(f"note_{student.id}", "").strip()[:250]
                RoundAttendance.objects.update_or_create(
                    evaluation_round=evaluation_round, student=student,
                    defaults={"status": status, "note": note},
                )
                updated += 1
            messages.success(request, f"{evaluation_round.name} 출결 {updated}명을 저장했습니다.")
        return redirect(f"/management/attendance/?round={evaluation_round.id}")

    rows = []
    stats = {"present": 0, "absent": 0, "excused": 0, "total": 0}
    if selected_round:
        students = list(Student.objects.filter(is_active=True, user__is_active=True).select_related("user").order_by("user__first_name", "user__username"))
        attendance_map = {a.student_id: a for a in RoundAttendance.objects.filter(evaluation_round=selected_round)}
        membership_map = {m.student_id: m for m in TeamMembership.objects.filter(team__evaluation_round=selected_round).select_related("team")}
        for student in students:
            attendance = attendance_map.get(student.id)
            status = attendance.status if attendance else RoundAttendance.Status.PRESENT
            row = {
                "student": student,
                "team": membership_map.get(student.id).team if membership_map.get(student.id) else None,
                "status": status,
                "note": attendance.note if attendance else "",
                "team_eval_allowed": status == RoundAttendance.Status.PRESENT,
                "personal_eval_allowed": True,
            }
            rows.append(row)
            stats[status] += 1
        stats["total"] = len(rows)

    return render(request, "admin_ui/attendance.html", _base_context(
        rounds=rounds, selected_round=selected_round, rows=rows, stats=stats,
        attendance_choices=RoundAttendance.Status.choices,
    ))
