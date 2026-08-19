from .common import *

@login_required
def hr_task_attachment_download(request, task_id):
    """역량 과제의 관리자 첨부파일을 관리자 또는 배정 학생에게 제공한다."""
    task = get_object_or_404(HRTask.objects.select_related("assignee__user"), pk=task_id)

    if not (request.user.is_staff or request.user.is_superuser):
        student = getattr(request.user, "student_profile", None)
        if not student or not student.is_active or task.assignee_id != student.id:
            messages.error(request, "본인에게 배정된 역량 과제의 첨부파일만 받을 수 있습니다.")
            return redirect("student_hr_tasks")

    if not task.attachment:
        raise Http404("첨부파일이 없습니다.")

    try:
        file_handle = task.attachment.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("첨부파일을 찾을 수 없습니다.")

    filename = task.attachment.name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return FileResponse(file_handle, as_attachment=True, filename=filename)


@login_required
def assignment_attachment_download(request, assignment_id):
    """과제 첨부파일을 브라우저 미리보기가 아닌 실제 다운로드로 제공한다."""
    assignment = get_object_or_404(Assignment, pk=assignment_id)

    # 관리자 또는 활성 수강생만 다운로드할 수 있다.
    if not (request.user.is_staff or request.user.is_superuser):
        student = getattr(request.user, "student_profile", None)
        if not student or not student.is_active:
            messages.error(request, "과제 첨부파일을 다운로드할 권한이 없습니다.")
            return redirect("login")

    if not assignment.attachment:
        raise Http404("첨부파일이 없습니다.")

    try:
        file_handle = assignment.attachment.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("첨부파일을 찾을 수 없습니다.")

    filename = assignment.attachment.name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return FileResponse(file_handle, as_attachment=True, filename=filename)

@login_required
def submission_attachment_download(request, submission_id):
    """조별과제 제출파일을 관리자 또는 해당 팀 학생에게 제공한다."""
    submission = get_object_or_404(
        TeamAssignmentSubmission.objects.select_related("team", "assignment__evaluation_round"),
        pk=submission_id,
    )
    if not (request.user.is_staff or request.user.is_superuser):
        student = getattr(request.user, "student_profile", None)
        if not student or not student.is_active:
            messages.error(request, "제출파일을 다운로드할 권한이 없습니다.")
            return redirect("login")
        if not TeamMembership.objects.filter(team=submission.team, student=student).exists():
            messages.error(request, "본인 팀의 제출파일만 다운로드할 수 있습니다.")
            return redirect("student_assignment_info")
    if not submission.attachment:
        raise Http404("첨부파일이 없습니다.")
    try:
        file_handle = submission.attachment.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("첨부파일을 찾을 수 없습니다.")
    filename = submission.attachment.name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return FileResponse(file_handle, as_attachment=True, filename=filename)


@login_required
def student_submission_attachment_download(request, submission_id):
    """개별과제 제출파일을 관리자 또는 제출 학생 본인에게 제공한다."""
    submission = get_object_or_404(
        StudentAssignmentSubmission.objects.select_related("student__user", "assignment__evaluation_round"),
        pk=submission_id,
    )
    if not (request.user.is_staff or request.user.is_superuser):
        student = getattr(request.user, "student_profile", None)
        if not student or not student.is_active or student.pk != submission.student_id:
            messages.error(request, "본인의 개별과제 제출파일만 다운로드할 수 있습니다.")
            return redirect("student_assignment_info")
    if not submission.attachment:
        raise Http404("첨부파일이 없습니다.")
    try:
        file_handle = submission.attachment.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("첨부파일을 찾을 수 없습니다.")
    filename = submission.attachment.name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return FileResponse(file_handle, as_attachment=True, filename=filename)


@student_required
def student_home(request):
    current_round = _display_round_for_student()
    my_team = _student_team(request.student, current_round) if current_round else None
    assignment = None
    assignments = []
    assignment_rows = []
    if current_round:
        assignments = [
            _decorate_assignment(item)
            for item in Assignment.objects.filter(evaluation_round=current_round).select_related("evaluation_round")
        ]
        assignment = assignments[0] if assignments else None
        current_round.status_display = current_round.get_status_display()

        for item in assignments:
            submitted = False
            if item.assignment_type == Assignment.AssignmentType.TEAM:
                submitted = bool(
                    my_team
                    and TeamAssignmentSubmission.objects.filter(assignment=item, team=my_team).exists()
                )
            else:
                submitted = StudentAssignmentSubmission.objects.filter(
                    assignment=item, student=request.student
                ).exists()
            assignment_rows.append({"assignment": item, "submitted": submitted})

    progress = _student_progress(request.student, current_round, my_team)
    team_members = []
    if my_team:
        memberships = (
            TeamMembership.objects.filter(team=my_team)
            .select_related("student__user")
            .order_by("student__user__first_name", "student__user__username")
        )
        for membership in memberships:
            member = membership.student
            member.team_role = membership.role.strip() or ("팀장" if membership.is_leader else "팀원")
            team_members.append(member)

    attendance = _attendance_for(request.student, current_round) if current_round else None
    absent_from_team_eval = bool(attendance and attendance.status in {RoundAttendance.Status.ABSENT, RoundAttendance.Status.EXCUSED})
    round_in_progress = bool(current_round and current_round.status == EvaluationRound.Status.IN_PROGRESS)
    round_ended = bool(current_round and current_round.status == EvaluationRound.Status.ENDED)
    team_eval_available = bool(
        round_in_progress and current_round.evaluation_started and not current_round.is_locked
        and my_team and not absent_from_team_eval
    )
    personal_eval_available = bool(
        round_in_progress and current_round.evaluation_started and not current_round.is_locked
        and my_team and (absent_from_team_eval or progress["team_total"] == progress["team_completed"])
    )

    result_available = False
    received_comment_count = 0
    admin_feedback_available = False
    self_review_completed = False
    feedback_written_count = 0
    if current_round:
        publish_setting = ResultPublishSetting.objects.filter(evaluation_round=current_round).first()
        now = timezone.now()
        result_available = bool(
            publish_setting
            and (publish_setting.is_published or (publish_setting.publish_at and publish_setting.publish_at <= now))
            and StudentResult.objects.filter(
                evaluation_round=current_round, student=request.student, is_excluded=False
            ).exists()
        )
        if result_available and publish_setting and publish_setting.show_comments:
            received_comment_count = PersonalEvaluation.objects.filter(
                evaluation_round=current_round,
                target_student=request.student,
                is_submitted=True,
            ).exclude(comment="").count()
            admin_feedback_available = AdminStudentComment.objects.filter(
                evaluation_round=current_round,
                student=request.student,
            ).exclude(comment="").exists()
        self_review_completed = SelfProjectReview.objects.filter(
            evaluation_round=current_round,
            student=request.student,
        ).exists()
        feedback_written_count = (
            TeamEvaluation.objects.filter(
                evaluation_round=current_round, evaluator=request.student, is_submitted=True
            ).exclude(comment="").count()
            + PersonalEvaluation.objects.filter(
                evaluation_round=current_round, evaluator=request.student, is_submitted=True
            ).exclude(comment="").count()
        )

    pending_assignment_count = sum(1 for row in assignment_rows if not row["submitted"])
    assignment_completed_count = len(assignment_rows) - pending_assignment_count
    team_remaining_count = max(0, progress["team_total"] - progress["team_completed"])
    personal_remaining_count = max(0, progress["personal_total"] - progress["personal_completed"])
    todo_total_count = len(assignment_rows) + progress["team_total"] + progress["personal_total"]
    todo_completed_count = assignment_completed_count + progress["team_completed"] + progress["personal_completed"]
    todo_remaining_count = max(0, todo_total_count - todo_completed_count)

    # 학생이 현재 평가를 수정할 수 있는지 홈에서 즉시 확인할 수 있게 요약한다.
    evaluation_edit_status = {
        "level": "waiting", "label": "평가 대기",
        "detail": "평가가 시작되면 입력할 수 있습니다.", "editable": False,
    }
    if current_round:
        all_eval_done = bool(
            (progress["team_total"] == 0 or progress["team_completed"] >= progress["team_total"])
            and (progress["personal_total"] == 0 or progress["personal_completed"] >= progress["personal_total"])
        )
        if current_round.status == EvaluationRound.Status.ENDED:
            evaluation_edit_status = {"level": "closed", "label": "수정 종료", "detail": "회차가 종료되어 평가를 수정할 수 없습니다.", "editable": False}
        elif current_round.is_locked:
            evaluation_edit_status = {"level": "paused", "label": "평가 일시 중단", "detail": "관리자가 재개하면 기존 평가를 다시 수정할 수 있습니다.", "editable": False}
        elif not current_round.evaluation_started:
            evaluation_edit_status = {"level": "waiting", "label": "평가 시작 전", "detail": "관리자가 평가를 시작하면 입력할 수 있습니다.", "editable": False}
        elif all_eval_done:
            evaluation_edit_status = {"level": "complete", "label": "제출 완료 · 수정 가능", "detail": "평가 종료 전까지 제출한 내용을 다시 수정할 수 있습니다.", "editable": True}
        else:
            evaluation_edit_status = {"level": "active", "label": "평가 진행 중", "detail": "임시 저장하거나 최종 제출할 수 있으며, 종료 전에는 다시 수정할 수 있습니다.", "editable": True}

    # Student-facing deadline cue. Keep this presentation-oriented so the
    # evaluation rules themselves remain untouched.
    deadline = None
    if current_round:
        remaining = current_round.end_at - timezone.now()
        remaining_seconds = int(remaining.total_seconds())
        if remaining_seconds <= 0:
            deadline = {"label": "마감", "detail": "평가 기간이 종료되었습니다.", "level": "closed"}
        elif remaining_seconds <= 6 * 60 * 60:
            hours = max(1, (remaining_seconds + 3599) // 3600)
            deadline = {"label": f"{hours}시간 남음", "detail": "마감이 임박했습니다. 남은 항목을 확인하세요.", "level": "critical"}
        elif remaining_seconds <= 24 * 60 * 60:
            hours = max(1, (remaining_seconds + 3599) // 3600)
            deadline = {"label": f"{hours}시간 남음", "detail": "오늘 안에 평가와 제출을 마무리해 주세요.", "level": "warning"}
        else:
            days = max(1, (remaining_seconds + 86399) // 86400)
            deadline = {"label": f"D-{days}", "detail": f"{current_round.end_at:%m.%d %H:%M} 마감", "level": "normal"}

    active_announcements = _active_announcements(request.student) if "_active_announcements" in globals() else Announcement.objects.none()
    recent_announcements = list(active_announcements[:3])

    read_announcement_ids = set(
        AnnouncementRead.objects.filter(
            student=request.student,
            announcement__in=active_announcements,
        ).values_list("announcement_id", flat=True)
    )
    unread_announcements = [item for item in active_announcements if item.id not in read_announcement_ids]
    unread_announcement_count = len(unread_announcements)
    urgent_announcement_count = sum(
        1 for item in unread_announcements if item.priority == Announcement.Priority.URGENT
    )
    unread_message_count = InternalMessage.objects.filter(
        recipient=request.student,
        read_at__isnull=True,
        recalled_at__isnull=True,
    ).count()

    growth_task_preview = list(
        HRTask.objects.filter(assignee=request.student)
        .exclude(status=HRTask.Status.COMPLETED)
        .order_by("due_date", "-created_at")[:3]
    )

    return render(request, "student/home.html", _base_context(
        current_round=current_round, my_team=my_team, assignment=assignment, assignments=assignments,
        growth_task_preview=growth_task_preview,
        assignment_rows=assignment_rows, pending_assignment_count=pending_assignment_count,
        progress=progress, team_members=team_members, team_eval_available=team_eval_available,
        personal_eval_available=personal_eval_available, recent_announcements=recent_announcements,
        attendance=attendance, absent_from_team_eval=absent_from_team_eval,
        round_in_progress=round_in_progress, round_ended=round_ended,
        result_available=result_available, received_comment_count=received_comment_count,
        admin_feedback_available=admin_feedback_available, self_review_completed=self_review_completed,
        feedback_written_count=feedback_written_count,
        unread_message_count=unread_message_count,
        unread_announcement_count=unread_announcement_count,
        urgent_announcement_count=urgent_announcement_count,
        deadline=deadline, evaluation_edit_status=evaluation_edit_status,
        todo_total_count=todo_total_count, todo_completed_count=todo_completed_count,
        todo_remaining_count=todo_remaining_count, team_remaining_count=team_remaining_count,
        personal_remaining_count=personal_remaining_count,
    ))


@student_required
def student_team_info(request):
    evaluation_round = _display_round_for_student()
    team = _student_team(request.student, evaluation_round) if evaluation_round else None
    team_members = []
    if team:
        team.status_display = "활동 중" if team.is_active else "비활성"
        memberships = (
            TeamMembership.objects.filter(team=team)
            .select_related("student__user")
            .order_by("student__user__first_name", "student__user__username")
        )
        for membership in memberships:
            member = membership.student
            member.team_role = membership.role.strip() or ("팀장" if membership.is_leader else "팀원")
            member.is_team_leader = membership.is_leader
            team_members.append(member)
    return render(request, "student/team_info.html", _base_context(
        evaluation_round=evaluation_round, team=team, team_members=team_members
    ))


@student_required
@transaction.atomic
def student_assignment_info(request):
    """현재 회차의 조별/개별 과제를 한 화면에서 조회하고 제출한다."""
    evaluation_round = _display_round_for_student()
    my_team = _student_team(request.student, evaluation_round) if evaluation_round else None
    can_submit = bool(
        evaluation_round and evaluation_round.status == EvaluationRound.Status.IN_PROGRESS
        and not evaluation_round.evaluation_started and not evaluation_round.is_locked
    )

    assignments = []
    if evaluation_round:
        assignments = list(
            Assignment.objects.filter(evaluation_round=evaluation_round)
            .select_related("evaluation_round").order_by("assignment_type", "id")
        )
        for assignment in assignments:
            _decorate_assignment(assignment)

    if request.method == "POST":
        if not evaluation_round:
            messages.error(request, "현재 진행 중인 회차가 없습니다.")
            return redirect("student_assignment_info")
        if not can_submit:
            messages.error(request, "과제 제출은 회차 시작 후 평가 시작 전까지만 수정할 수 있습니다.")
            return redirect("student_assignment_info")

        raw_assignment_id = request.POST.get("assignment_id", "").strip()
        assignment = get_object_or_404(Assignment, pk=raw_assignment_id, evaluation_round=evaluation_round)
        submission_url = request.POST.get("submission_url", "").strip()
        note = request.POST.get("note", "").strip()
        attachment = request.FILES.get("attachment")

        if assignment.assignment_type == Assignment.AssignmentType.TEAM:
            if not my_team:
                messages.error(request, "조별과제 제출을 위해 먼저 팀에 배정되어야 합니다.")
                return redirect("student_assignment_info")
            submission = TeamAssignmentSubmission.objects.filter(assignment=assignment, team=my_team).first()
            if not submission_url and not note and not attachment and not (submission and submission.attachment):
                messages.error(request, "제출 링크, 파일, 메모 중 하나 이상을 입력해 주세요.")
                return redirect("student_assignment_info")
            submission, _ = TeamAssignmentSubmission.objects.get_or_create(
                assignment=assignment, team=my_team, defaults={"submitted_by": request.student}
            )
            submission.submitted_by = request.student
            success_label = f"{my_team.name} 조별과제"
        else:
            submission = StudentAssignmentSubmission.objects.filter(assignment=assignment, student=request.student).first()
            if not submission_url and not note and not attachment and not (submission and submission.attachment):
                messages.error(request, "제출 링크, 파일, 메모 중 하나 이상을 입력해 주세요.")
                return redirect("student_assignment_info")
            submission, _ = StudentAssignmentSubmission.objects.get_or_create(
                assignment=assignment, student=request.student
            )
            success_label = "개별과제"

        submission.submission_url = submission_url
        submission.note = note
        if attachment:
            submission.attachment = attachment
        submission.submitted_at = timezone.now()
        submission.save()
        messages.success(request, f"{success_label} 제출 내용을 저장했습니다.")
        return redirect("student_assignment_info")

    rows = []
    for assignment in assignments:
        if assignment.assignment_type == Assignment.AssignmentType.TEAM:
            submission = None
            if my_team:
                submission = TeamAssignmentSubmission.objects.filter(
                    assignment=assignment, team=my_team
                ).select_related("submitted_by__user", "commented_by").first()
            rows.append({"assignment": assignment, "submission": submission, "is_team": True, "can_access": bool(my_team)})
        else:
            submission = StudentAssignmentSubmission.objects.filter(
                assignment=assignment, student=request.student
            ).first()
            rows.append({"assignment": assignment, "submission": submission, "is_team": False, "can_access": True})

    return render(request, "student/assignment_info.html", _base_context(
        evaluation_round=evaluation_round, assignment_rows=rows, my_team=my_team,
        can_submit=can_submit, presentation_schedule=[]
    ))


@student_required
@transaction.atomic
def student_team_evaluation(request):
    evaluation_round = _current_round_for_evaluation()
    if not evaluation_round:
        return render(request, "student/team_evaluation.html", _base_context(evaluation_open=False, evaluation_locked=False, target_teams=[], criteria=[]))
    if evaluation_round.is_locked:
        if request.method == "POST":
            messages.error(request, "관리자가 현재 평가를 일시 중단했습니다. 평가 재개 후 다시 제출해 주세요.")
        return render(request, "student/team_evaluation.html", _base_context(
            evaluation_open=False, evaluation_locked=True, evaluation_round=evaluation_round, target_teams=[], criteria=[]
        ))

    attendance = _attendance_for(request.student, evaluation_round)
    if attendance and attendance.status in {RoundAttendance.Status.ABSENT, RoundAttendance.Status.EXCUSED}:
        if request.method == "POST":
            messages.error(request, "발표 당일 결석/공결 처리되어 다른 팀 평가는 제출할 수 없습니다.")
        return render(request, "student/team_evaluation.html", _base_context(
            evaluation_open=False, attendance_blocked=True, attendance=attendance,
            evaluation_round=evaluation_round, target_teams=[], criteria=[]
        ))

    my_team = _student_team(request.student, evaluation_round)
    template = _template_for(evaluation_round, EvaluationTemplate.EvaluationType.TEAM)
    criteria = list(template.criteria.all().order_by("order", "id")) if template else []
    target_teams = list(
        Team.objects.filter(evaluation_round=evaluation_round, is_active=True)
        .exclude(pk=getattr(my_team, "pk", None))
        .annotate(member_count=Count("memberships"))
        .order_by("name")
    )

    existing = {
        e.target_team_id: e
        for e in TeamEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            evaluator=request.student,
            target_team__in=target_teams,
        ).prefetch_related("scores")
    }
    for team in target_teams:
        evaluation = existing.get(team.id)
        team.is_submitted = bool(evaluation and evaluation.is_submitted)
        team.is_draft = bool(evaluation and not evaluation.is_submitted and evaluation.scores.exists())

    selected_team_id = request.POST.get("target_team_id") or request.GET.get("team")
    selected_team = next((t for t in target_teams if str(t.id) == str(selected_team_id)), None)
    saved_scores = {}
    saved_comment = ""

    if request.method == "POST":
        if not selected_team:
            messages.error(request, "평가할 팀을 선택하세요.")
        elif not criteria:
            messages.error(request, "등록된 팀 평가 항목이 없습니다.")
        else:
            action = request.POST.get("action", "draft")
            if action == "submit" and not _criteria_complete(request.POST, criteria):
                messages.error(request, "필수 평가 항목을 모두 입력해야 최종 제출할 수 있습니다.")
            else:
                evaluation, _ = TeamEvaluation.objects.get_or_create(
                    evaluation_round=evaluation_round,
                    evaluator=request.student,
                    target_team=selected_team,
                )
                evaluation.comment = request.POST.get("comment", "").strip()
                evaluation.is_submitted = action == "submit"
                evaluation.submitted_at = timezone.now() if evaluation.is_submitted else None
                evaluation.save()
                _save_scores(evaluation, TeamEvaluationScore, criteria, request.POST)
                if evaluation.is_submitted:
                    _recalculate_round_results(evaluation_round)
                    messages.success(request, f"{selected_team.name} 평가를 최종 제출했습니다. 평가 종료 전에는 다시 수정할 수 있습니다.")
                else:
                    messages.success(request, f"{selected_team.name} 평가를 임시 저장했습니다.")
                return redirect(f"/team-evaluation/?team={selected_team.id}")

    if selected_team:
        evaluation = existing.get(selected_team.id) or TeamEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            evaluator=request.student,
            target_team=selected_team,
        ).first()
        if evaluation:
            saved_scores = {score.criterion_id: score.score for score in evaluation.scores.all()}
            saved_comment = evaluation.comment

    submitted_count = sum(1 for t in target_teams if t.is_submitted)
    draft_count = sum(1 for t in target_teams if t.is_draft)
    remaining_count = max(len(target_teams) - submitted_count, 0)
    next_team = next((t for t in target_teams if not t.is_submitted and (not selected_team or t.id != selected_team.id)), None)
    selected_position = next((i for i, t in enumerate(target_teams, start=1) if selected_team and t.id == selected_team.id), None)
    selected_evaluation = existing.get(selected_team.id) if selected_team else None
    return render(
        request,
        "student/team_evaluation.html",
        _base_context(
            evaluation_open=True,
            evaluation_round=evaluation_round,
            my_team=my_team,
            target_teams=target_teams,
            criteria=criteria,
            selected_team=selected_team,
            saved_scores=saved_scores,
            saved_comment=saved_comment,
            submitted_count=submitted_count,
            draft_count=draft_count,
            remaining_count=remaining_count,
            total_count=len(target_teams),
            next_team=next_team,
            selected_position=selected_position,
            selected_evaluation=selected_evaluation,
        ),
    )

@student_required
@transaction.atomic
def student_personal_evaluation(request):
    evaluation_round = _current_round_for_evaluation()
    if not evaluation_round:
        return render(request, "student/personal_evaluation.html", _base_context(evaluation_open=False, evaluation_locked=False, target_members=[], criteria=[]))
    if evaluation_round.is_locked:
        if request.method == "POST":
            messages.error(request, "관리자가 현재 평가를 일시 중단했습니다. 평가 재개 후 다시 제출해 주세요.")
        return render(request, "student/personal_evaluation.html", _base_context(
            evaluation_open=False, evaluation_locked=True, evaluation_round=evaluation_round, target_members=[], criteria=[]
        ))

    my_team = _student_team(request.student, evaluation_round)
    if not my_team:
        return render(request, "student/personal_evaluation.html", _base_context(evaluation_open=False, no_team=True, target_members=[], criteria=[]))

    # 출석자는 다른 팀 평가를 모두 제출한 뒤 개인 평가를 연다.
    # 결석/공결자는 다른 팀 평가 의무를 면제하고 같은 팀원 개인 평가는 허용한다.
    attendance = _attendance_for(request.student, evaluation_round)
    absent_from_team_eval = bool(attendance and attendance.status in {RoundAttendance.Status.ABSENT, RoundAttendance.Status.EXCUSED})
    target_team_count = 0 if absent_from_team_eval else Team.objects.filter(
        evaluation_round=evaluation_round, is_active=True
    ).exclude(pk=my_team.pk).count()
    submitted_team_count = TeamEvaluation.objects.filter(
        evaluation_round=evaluation_round,
        evaluator=request.student,
        is_submitted=True,
    ).count()
    team_evaluation_complete = absent_from_team_eval or target_team_count == 0 or submitted_team_count >= target_team_count

    template = _template_for(evaluation_round, EvaluationTemplate.EvaluationType.PERSONAL)
    criteria = list(template.criteria.all().order_by("order", "id")) if template else []
    target_members = list(
        Student.objects.filter(
            team_memberships__team=my_team,
            is_active=True,
            user__is_active=True,
        )
        .exclude(pk=request.student.pk)
        .select_related("user")
        .distinct()
        .order_by("user__first_name", "user__username")
    )

    existing = {
        e.target_student_id: e
        for e in PersonalEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            evaluator=request.student,
            target_student__in=target_members,
        ).prefetch_related("scores")
    }
    for member in target_members:
        evaluation = existing.get(member.id)
        member.is_submitted = bool(evaluation and evaluation.is_submitted)
        member.is_draft = bool(evaluation and not evaluation.is_submitted and (evaluation.scores.exists() or evaluation.comment))

    selected_member_id = request.POST.get("target_student_id") or request.GET.get("member")
    selected_member = next((m for m in target_members if str(m.id) == str(selected_member_id)), None)
    saved_scores = {}
    saved_comment = ""

    if request.method == "POST":
        if not team_evaluation_complete:
            messages.error(request, "모든 다른 팀의 팀 평가를 먼저 최종 제출해야 개인 평가를 할 수 있습니다.")
        elif not selected_member:
            messages.error(request, "평가할 팀원을 선택하세요.")
        elif not criteria:
            messages.error(request, "등록된 개인 평가 항목이 없습니다.")
        else:
            action = request.POST.get("action", "draft")
            invalid_personal_score = False
            for criterion in criteria:
                raw_score = request.POST.get(f"criterion_{criterion.id}")
                if not raw_score:
                    continue
                try:
                    score = int(raw_score)
                except (TypeError, ValueError):
                    invalid_personal_score = True
                    break
                if score not in {1, 2, 3, 4, 5}:
                    invalid_personal_score = True
                    break

            if action == "submit" and not _criteria_complete(request.POST, criteria):
                messages.error(request, "필수 평가 항목을 모두 입력해야 최종 제출할 수 있습니다.")
            elif invalid_personal_score:
                messages.error(request, "개인 평가 점수는 1점부터 5점까지만 사용할 수 있습니다.")
            else:
                evaluation, _ = PersonalEvaluation.objects.get_or_create(
                    evaluation_round=evaluation_round,
                    evaluator=request.student,
                    target_student=selected_member,
                )
                evaluation.comment = request.POST.get("comment", "").strip()
                evaluation.is_submitted = action == "submit"
                evaluation.submitted_at = timezone.now() if evaluation.is_submitted else None
                evaluation.save()
                _save_scores(evaluation, PersonalEvaluationScore, criteria, request.POST)
                if evaluation.is_submitted:
                    _recalculate_round_results(evaluation_round)
                    messages.success(request, f"{selected_member.name} 평가를 최종 제출했습니다. 평가 종료 전에는 다시 수정할 수 있습니다.")
                else:
                    messages.success(request, f"{selected_member.name} 평가를 임시 저장했습니다.")
                return redirect(f"/personal-evaluation/?member={selected_member.id}")

    if selected_member:
        evaluation = existing.get(selected_member.id) or PersonalEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            evaluator=request.student,
            target_student=selected_member,
        ).first()
        if evaluation:
            saved_scores = {score.criterion_id: score.score for score in evaluation.scores.all()}
            saved_comment = evaluation.comment

    submitted_count = sum(1 for m in target_members if m.is_submitted)
    draft_count = sum(1 for m in target_members if m.is_draft)
    remaining_count = max(len(target_members) - submitted_count, 0)
    next_member = next((m for m in target_members if not m.is_submitted and (not selected_member or m.id != selected_member.id)), None)
    selected_position = next((i for i, m in enumerate(target_members, start=1) if selected_member and m.id == selected_member.id), None)
    selected_evaluation = existing.get(selected_member.id) if selected_member else None

    return render(
        request,
        "student/personal_evaluation.html",
        _base_context(
            evaluation_open=True,
            evaluation_round=evaluation_round,
            my_team=my_team,
            team_evaluation_complete=team_evaluation_complete,
            submitted_team_count=submitted_team_count,
            target_team_count=target_team_count,
            target_members=target_members,
            criteria=criteria,
            selected_member=selected_member,
            saved_scores=saved_scores,
            saved_comment=saved_comment,
            submitted_count=submitted_count,
            draft_count=draft_count,
            remaining_count=remaining_count,
            total_count=len(target_members),
            next_member=next_member,
            selected_position=selected_position,
            selected_evaluation=selected_evaluation,
            attendance=attendance,
            absent_from_team_eval=absent_from_team_eval,
        ),
    )

@student_required
def student_evaluation_status(request):
    evaluation_round = _current_round_for_evaluation() or EvaluationRound.objects.order_by("-start_at").first()
    if not evaluation_round:
        return render(request, "student/evaluation_status.html", _base_context(
            evaluation_round=None, team_statuses=[], personal_statuses=[],
            progress=_student_progress(request.student, None, None),
        ))

    evaluation_round.status_display = evaluation_round.get_status_display()
    my_team = _student_team(request.student, evaluation_round)
    attendance = _attendance_for(request.student, evaluation_round)
    absent_from_team_eval = bool(attendance and attendance.status in {RoundAttendance.Status.ABSENT, RoundAttendance.Status.EXCUSED})
    target_teams = [] if absent_from_team_eval else (list(
        Team.objects.filter(evaluation_round=evaluation_round, is_active=True)
        .exclude(pk=getattr(my_team, "pk", None))
        .annotate(member_count=Count("memberships"))
        .order_by("name")
    ) if my_team else [])
    team_eval_map = {
        e.target_team_id: e for e in TeamEvaluation.objects.filter(
            evaluation_round=evaluation_round, evaluator=request.student
        )
    }
    team_statuses = []
    for team in target_teams:
        evaluation = team_eval_map.get(team.id)
        if evaluation and evaluation.is_submitted:
            status_display = "제출 완료"
        elif evaluation:
            status_display = "임시 저장"
        else:
            status_display = "미평가"
        team_statuses.append({
            "team_name": team.name,
            "project_title": team.project_title or "-",
            "status_display": status_display,
            "submitted": bool(evaluation and evaluation.is_submitted),
            "updated_at": evaluation.updated_at if evaluation else None,
        })

    target_members = []
    if my_team:
        target_members = list(
            Student.objects.filter(team_memberships__team=my_team)
            .exclude(pk=request.student.pk)
            .select_related("user")
            .distinct()
        )
    personal_eval_map = {
        e.target_student_id: e for e in PersonalEvaluation.objects.filter(
            evaluation_round=evaluation_round, evaluator=request.student
        )
    }
    personal_statuses = []
    for member in target_members:
        evaluation = personal_eval_map.get(member.id)
        personal_statuses.append({
            "student_name": member.name,
            "status_display": "제출 완료" if evaluation and evaluation.is_submitted else "미평가",
            "submitted": bool(evaluation and evaluation.is_submitted),
            "updated_at": evaluation.updated_at if evaluation else None,
        })

    progress = _student_progress(request.student, evaluation_round, my_team)
    return render(request, "student/evaluation_status.html", _base_context(
        evaluation_round=evaluation_round,
        my_team=my_team,
        team_statuses=team_statuses,
        personal_statuses=personal_statuses,
        progress=progress,
    ))

@student_required
def student_results(request):
    """학생 본인에게 공개된 결과를 회차별로 선택해서 보여준다."""
    now = timezone.now()
    settings_qs = list(
        ResultPublishSetting.objects.filter(evaluation_round__student_results__student=request.student)
        .select_related("evaluation_round")
        .distinct()
        .order_by("-evaluation_round__start_at")
    )

    visible_settings = [
        setting for setting in settings_qs
        if setting.is_published or (setting.publish_at and setting.publish_at <= now)
    ]

    selected_round_id = (request.GET.get("round") or "").strip()
    publish_setting = None
    if selected_round_id.isdigit():
        publish_setting = next(
            (
                setting for setting in visible_settings
                if setting.evaluation_round_id == int(selected_round_id)
            ),
            None,
        )

    if publish_setting is None and visible_settings:
        publish_setting = visible_settings[0]

    if not publish_setting:
        return render(
            request,
            "student/results.html",
            _base_context(result_published=False, result={}, available_result_rounds=[]),
        )

    evaluation_round = publish_setting.evaluation_round
    student_result = StudentResult.objects.filter(
        evaluation_round=evaluation_round, student=request.student, is_excluded=False
    ).first()
    if not student_result:
        return render(
            request,
            "student/results.html",
            _base_context(
                result_published=False,
                result={},
                available_result_rounds=[
                    {
                        "id": setting.evaluation_round_id,
                        "name": setting.evaluation_round.name,
                        "selected": setting.evaluation_round_id == evaluation_round.id,
                    }
                    for setting in visible_settings
                ],
            ),
        )

    membership = TeamMembership.objects.filter(
        team__evaluation_round=evaluation_round, student=request.student
    ).select_related("team").first()
    team = membership.team if membership else None
    team_result = TeamResult.objects.filter(
        evaluation_round=evaluation_round, team=team, is_excluded=False
    ).first() if team else None

    # BR-10: 개인 점수 비공개 시 템플릿에 숨겨두는 수준이 아니라
    # 서버 context 자체에서 개인 점수/최종점수 상세를 제거한다.
    breakdown = []
    comparison_summary = None
    if publish_setting.show_personal_score:
        peer_results = StudentResult.objects.filter(
            evaluation_round=evaluation_round,
            is_excluded=False,
        )
        averages = peer_results.aggregate(
            team_avg=Avg("team_score"),
            personal_avg=Avg("personal_score"),
            final_avg=Avg("final_score"),
        )

        def _comparison_item(label, score, average):
            delta = score - average if average is not None else None
            return {
                "label": label,
                "score": score,
                "average": average,
                "delta": delta,
                "compare_label": (
                    "평균보다 높음" if delta is not None and delta > 0
                    else "평균보다 낮음" if delta is not None and delta < 0
                    else "평균과 동일"
                ) if delta is not None else "-",
            }

        breakdown = [
            _comparison_item(
                f"팀 평가 점수 ({evaluation_round.team_weight}%)",
                student_result.team_score,
                averages["team_avg"],
            ),
            _comparison_item(
                f"개인 평가 점수 ({evaluation_round.personal_weight}%)",
                student_result.personal_score,
                averages["personal_avg"],
            ),
            _comparison_item(
                "최종 점수",
                student_result.final_score,
                averages["final_avg"],
            ),
        ]
        comparison_summary = {
            "participant_count": peer_results.count(),
            "final_average": averages["final_avg"],
            "final_delta": (
                student_result.final_score - averages["final_avg"]
                if averages["final_avg"] is not None else None
            ),
        }

    # 개인 평가 문항별 평균을 레이더 차트용 데이터로 구성한다.
    # 비정상 평가 데이터가 DB에 남아 있어도 같은 팀 구성원 간 평가만 집계한다.
    radar_chart = None
    if publish_setting.show_personal_score:
        memberships = TeamMembership.objects.filter(
            team__evaluation_round=evaluation_round
        ).values_list("student_id", "team_id")
        student_team_map = {student_id: team_id for student_id, team_id in memberships}

        personal_evaluations = (
            PersonalEvaluation.objects.filter(
                evaluation_round=evaluation_round,
                is_submitted=True,
            )
            .prefetch_related("scores__criterion__template")
        )

        mine = {}
        cohort = {}
        criterion_meta = {}
        for evaluation in personal_evaluations:
            evaluator_team = student_team_map.get(evaluation.evaluator_id)
            target_team = student_team_map.get(evaluation.target_student_id)
            if (
                not evaluator_team
                or evaluator_team != target_team
                or evaluation.evaluator_id == evaluation.target_student_id
            ):
                continue

            for score_row in evaluation.scores.all():
                criterion = score_row.criterion
                if criterion.template.evaluation_type != EvaluationTemplate.EvaluationType.PERSONAL:
                    continue
                key = criterion.id
                criterion_meta[key] = {
                    "label": criterion.title,
                    "max_score": criterion.max_score or 5,
                    "order": criterion.order,
                }
                cohort.setdefault(key, []).append(float(score_row.score))
                if evaluation.target_student_id == request.student.id:
                    mine.setdefault(key, []).append(float(score_row.score))

        radar_items = []
        for criterion_id, meta in sorted(
            criterion_meta.items(), key=lambda item: (item[1]["order"], item[0])
        ):
            mine_scores = mine.get(criterion_id, [])
            if not mine_scores:
                continue
            my_avg = sum(mine_scores) / len(mine_scores)
            cohort_scores = cohort.get(criterion_id, [])
            cohort_avg = sum(cohort_scores) / len(cohort_scores) if cohort_scores else 0
            max_score = float(meta["max_score"])
            radar_items.append({
                "label": meta["label"],
                "score": round(my_avg, 2),
                "average": round(cohort_avg, 2),
                "max_score": max_score,
                "score_percent": round((my_avg / max_score) * 100, 2) if max_score else 0,
                "average_percent": round((cohort_avg / max_score) * 100, 2) if max_score else 0,
            })

        if len(radar_items) >= 3:
            radar_chart = {"items": radar_items}

    # 공개된 과거 회차의 개인 최종점수 추이.
    # 각 회차가 실제 공개 상태이며 개인 점수 공개가 허용된 경우만 포함한다.
    score_history = []
    history_settings = (
        ResultPublishSetting.objects.filter(
            evaluation_round__student_results__student=request.student,
            show_personal_score=True,
        )
        .select_related("evaluation_round")
        .distinct()
        .order_by("evaluation_round__start_at")
    )
    for history_setting in history_settings:
        if not (
            history_setting.is_published
            or (history_setting.publish_at and history_setting.publish_at <= now)
        ):
            continue
        history_result = StudentResult.objects.filter(
            evaluation_round=history_setting.evaluation_round,
            student=request.student,
            is_excluded=False,
        ).first()
        if not history_result or history_result.final_score is None:
            continue
        score_history.append(
            {
                "round_id": history_setting.evaluation_round_id,
                "round_name": history_setting.evaluation_round.name,
                "start_at": history_setting.evaluation_round.start_at,
                "team_score": history_result.team_score,
                "personal_score": history_result.personal_score,
                "final_score": history_result.final_score,
                "rank": history_result.rank if history_setting.show_overall_rank else None,
                "is_selected": history_setting.evaluation_round_id == evaluation_round.id,
            }
        )

    comments = []
    admin_feedback = None
    if publish_setting.show_comments:
        comments = list(
            PersonalEvaluation.objects.filter(
                evaluation_round=evaluation_round,
                target_student=request.student,
                is_submitted=True,
            )
            .exclude(comment="")
            .values_list("comment", flat=True)
        )
        admin_feedback = (
            AdminStudentComment.objects.filter(
                evaluation_round=evaluation_round,
                student=request.student,
            )
            .select_related("created_by")
            .first()
        )

    team_rankings = []
    if publish_setting.show_all_team_ranks:
        team_rankings = list(
            TeamResult.objects.filter(evaluation_round=evaluation_round, is_excluded=False)
            .select_related("team")
            .order_by("rank", "team__name")
        )

    first_team = None
    if publish_setting.show_team_first_place:
        first_team = (
            TeamResult.objects.filter(evaluation_round=evaluation_round, rank=1, is_excluded=False)
            .select_related("team")
            .first()
        )

    result = {
        "round_id": evaluation_round.id,
        "round_name": evaluation_round.name,
        "team_name": team.name if team else "-",
        "team_rank": team_result.rank if (team_result and publish_setting.show_all_team_ranks) else None,
        "team_score": student_result.team_score if publish_setting.show_personal_score else None,
        "personal_score": student_result.personal_score if publish_setting.show_personal_score else None,
        "final_score": student_result.final_score if publish_setting.show_personal_score else None,
        "overall_rank": student_result.rank if publish_setting.show_overall_rank else None,
        "breakdown": breakdown,
        "comparison_summary": comparison_summary,
        "radar_chart": radar_chart,
        "score_history": score_history if publish_setting.show_personal_score else [],
        "comments": comments,
        "admin_feedback": admin_feedback,
        "team_rankings": team_rankings,
        "first_team": first_team,
        "show_personal_score": publish_setting.show_personal_score,
        "show_overall_rank": publish_setting.show_overall_rank,
    }
    available_result_rounds = [
        {
            "id": setting.evaluation_round_id,
            "name": setting.evaluation_round.name,
            "selected": setting.evaluation_round_id == evaluation_round.id,
        }
        for setting in visible_settings
    ]
    return render(
        request,
        "student/results.html",
        _base_context(
            result_published=True,
            result=result,
            available_result_rounds=available_result_rounds,
        ),
    )

@student_required
def student_profile(request):
    """학생 마이페이지: 기본 정보 수정, 비밀번호 설정/변경, 평가 이력 조회."""
    student = request.student

    if request.method == "POST":
        action = request.POST.get("action", "profile")

        if action == "profile":
            profile_form = StudentProfileForm(request.POST, student=student)
            if profile_form.is_valid():
                user = student.user
                user.first_name = profile_form.cleaned_data["name"]
                user.last_name = ""
                user.save(update_fields=["first_name", "last_name"])
                student.affiliation = profile_form.cleaned_data["affiliation"]
                student.save(update_fields=["affiliation", "updated_at"])
                messages.success(request, "프로필 정보를 저장했습니다.")
                return redirect("student_profile")
        else:
            profile_form = StudentProfileForm(student=student)
    else:
        profile_form = StudentProfileForm(student=student)

    if request.method == "POST" and request.POST.get("action") == "password":
        if request.user.has_usable_password():
            password_form = PasswordChangeForm(request.user, request.POST)
        else:
            password_form = SetPasswordForm(request.user, request.POST)
        if password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "비밀번호를 변경했습니다.")
            return redirect("student_profile")
    else:
        password_form = PasswordChangeForm(request.user) if request.user.has_usable_password() else SetPasswordForm(request.user)

    now = timezone.now()
    round_ids = set(
        TeamMembership.objects.filter(student=student).values_list("team__evaluation_round_id", flat=True)
    )
    round_ids.update(TeamEvaluation.objects.filter(evaluator=student).values_list("evaluation_round_id", flat=True))
    round_ids.update(PersonalEvaluation.objects.filter(evaluator=student).values_list("evaluation_round_id", flat=True))
    round_ids.update(StudentResult.objects.filter(student=student).values_list("evaluation_round_id", flat=True))

    history = []
    for evaluation_round in EvaluationRound.objects.filter(id__in=round_ids).order_by("-start_at"):
        membership = (
            TeamMembership.objects.filter(student=student, team__evaluation_round=evaluation_round)
            .select_related("team")
            .first()
        )
        team_qs = TeamEvaluation.objects.filter(evaluation_round=evaluation_round, evaluator=student)
        personal_qs = PersonalEvaluation.objects.filter(evaluation_round=evaluation_round, evaluator=student)
        result = StudentResult.objects.filter(evaluation_round=evaluation_round, student=student).first()
        publish_setting = ResultPublishSetting.objects.filter(evaluation_round=evaluation_round).first()
        result_published = bool(
            publish_setting and (publish_setting.is_published or (publish_setting.publish_at and publish_setting.publish_at <= now))
        )
        history.append({
            "round": evaluation_round,
            "team": membership.team if membership else None,
            "team_submitted": team_qs.filter(is_submitted=True).count(),
            "team_saved": team_qs.filter(is_submitted=False).count(),
            "personal_submitted": personal_qs.filter(is_submitted=True).count(),
            "personal_saved": personal_qs.filter(is_submitted=False).count(),
            "result": result if result_published else None,
            "result_published": result_published,
        })

    social_accounts = []
    try:
        for account in request.user.socialaccount_set.all():
            provider_name = {"google": "Google", "kakao": "Kakao"}.get(account.provider, account.provider.title())
            social_accounts.append({"provider": account.provider, "name": provider_name})
    except Exception:
        social_accounts = []

    current_round = _display_round_for_student()
    current_team = _student_team(student, current_round) if current_round else None
    skill_profiles = list(
        StudentSkill.objects.filter(student=student)
        .select_related("skill")
        .order_by("-score", "skill__name")
    )
    recent_skill_updates = list(
        HRTaskSkillUpdate.objects.filter(student=student)
        .select_related("skill", "task")
        .order_by("-created_at")[:8]
    )

    return render(request, "student/profile.html", _base_context(
        profile_form=profile_form,
        password_form=password_form,
        password_mode="change" if request.user.has_usable_password() else "set",
        history=history,
        social_accounts=social_accounts,
        current_round=current_round,
        current_team=current_team,
        skill_profiles=skill_profiles,
        recent_skill_updates=recent_skill_updates,
    ))

@student_required
@require_POST
def student_announcement_read(request, announcement_id):
    """로그인 학생이 팝업 공지를 명시적으로 확인했을 때 읽음 기록을 남긴다."""
    announcement = get_object_or_404(_active_announcements(request.student), pk=announcement_id)
    AnnouncementRead.objects.get_or_create(
        student=request.student,
        announcement=announcement,
    )
    return _redirect_back(request, "student_home")


@student_required
def student_feedback(request):
    """튜터 개인 피드백을 회차별로 보여준다. 읽음 처리는 학생이 직접 누를 때만 한다."""
    feedbacks = list(
        AdminStudentComment.objects.filter(student=request.student)
        .select_related("evaluation_round", "created_by")
        .order_by("-evaluation_round__start_at", "-updated_at")
    )
    for item in feedbacks:
        item.was_unread = item.read_at is None

    return render(
        request,
        "student/feedback.html",
        _base_context(
            feedbacks=feedbacks,
            unread_feedback_count=sum(1 for item in feedbacks if item.was_unread),
        ),
    )


@student_required
@require_POST
def student_feedback_read(request, feedback_id):
    """본인에게 온 튜터 피드백 한 건을 명시적으로 읽음 처리한다."""
    feedback = get_object_or_404(
        AdminStudentComment,
        pk=feedback_id,
        student=request.student,
    )
    if feedback.read_at is None:
        feedback.read_at = timezone.now()
        feedback.save(update_fields=["read_at", "updated_at"])
        messages.success(request, "튜터 피드백을 읽음 처리했습니다.")
    return redirect("student_feedback")


@student_required
def student_notifications(request):
    announcements = list(_active_announcements(request.student)[:50])
    read_ids = set(
        AnnouncementRead.objects.filter(student=request.student, announcement__in=announcements)
        .values_list("announcement_id", flat=True)
    )
    for announcement in announcements:
        announcement.was_unread = announcement.id not in read_ids
    AnnouncementRead.objects.bulk_create(
        [AnnouncementRead(student=request.student, announcement=a) for a in announcements if a.id not in read_ids],
        ignore_conflicts=True,
    )

    notices = []
    current_round = _display_round_for_student()
    if current_round:
        progress = _student_progress(request.student, current_round, _student_team(request.student, current_round))
        now = timezone.now()
        if current_round.is_locked:
            notices.append({"level": "warning", "icon": "bi-lock-fill", "title": "평가가 일시 중단되었습니다.", "body": f"{current_round.name} 회차는 관리자가 재개할 때까지 저장·제출할 수 없습니다.", "url": "student_evaluation_status"})
        elif current_round.status == EvaluationRound.Status.IN_PROGRESS:
            remain = current_round.end_at - now
            if timedelta(0) <= remain <= timedelta(days=2):
                hours = max(int(remain.total_seconds() // 3600), 0)
                notices.append({"level": "danger", "icon": "bi-alarm-fill", "title": "평가 마감이 임박했습니다.", "body": f"{current_round.name} 마감까지 약 {hours}시간 남았습니다.", "url": "student_evaluation_status"})
            if progress["team_completed"] < progress["team_total"]:
                notices.append({"level": "info", "icon": "bi-people-fill", "title": "완료하지 않은 팀 평가가 있습니다.", "body": f"팀 평가 {progress['team_total'] - progress['team_completed']}건이 남아 있습니다.", "url": "student_team_evaluation"})
            elif progress["personal_completed"] < progress["personal_total"]:
                notices.append({"level": "info", "icon": "bi-person-check-fill", "title": "완료하지 않은 개인 평가가 있습니다.", "body": f"개인 평가 {progress['personal_total'] - progress['personal_completed']}건이 남아 있습니다.", "url": "student_personal_evaluation"})

        publish_setting = ResultPublishSetting.objects.filter(evaluation_round=current_round).first()
        if publish_setting and publish_setting.is_published and (not publish_setting.publish_at or publish_setting.publish_at <= now):
            notices.append({"level": "success", "icon": "bi-bar-chart-fill", "title": "평가 결과가 공개되었습니다.", "body": f"{current_round.name} 결과를 확인할 수 있습니다.", "url": "student_results"})

    return render(request, "student/notifications.html", _base_context(
        announcements=announcements,
        notices=notices,
        current_round=current_round,
    ))


@student_required
def student_self_review(request):
    """종료된 프로젝트 회차에 대한 학생 자기평가/회고를 작성한다."""
    ended_rounds = list(
        EvaluationRound.objects.filter(
            status=EvaluationRound.Status.ENDED,
            teams__memberships__student=request.student,
        )
        .distinct()
        .order_by("-start_at")
    )

    selected_round = None
    raw_round_id = (request.POST.get("evaluation_round_id") or request.GET.get("round") or "").strip()
    if raw_round_id:
        selected_round = next((round_obj for round_obj in ended_rounds if str(round_obj.id) == raw_round_id), None)
        if selected_round is None and request.method == "POST":
            messages.error(request, "자기평가를 작성할 수 없는 회차입니다.")
            return redirect("student_self_review")
    elif ended_rounds:
        selected_round = ended_rounds[0]

    review = None
    if selected_round:
        review = SelfProjectReview.objects.filter(
            evaluation_round=selected_round,
            student=request.student,
        ).first()

    if request.method == "POST":
        if not selected_round:
            messages.error(request, "자기평가를 작성할 수 있는 종료 회차가 없습니다.")
            return redirect("student_self_review")

        form = SelfProjectReviewForm(request.POST, instance=review)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.evaluation_round = selected_round
            saved.student = request.student
            try:
                saved.full_clean()
                saved.save()
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, f"{selected_round.name} 프로젝트 회고를 저장했습니다.")
                return redirect(f"{reverse('student_self_review')}?round={selected_round.id}")
    else:
        form = SelfProjectReviewForm(instance=review) if selected_round else SelfProjectReviewForm()

    reviews = {
        item.evaluation_round_id: item
        for item in SelfProjectReview.objects.filter(student=request.student).select_related("evaluation_round")
    }

    return render(request, "student/self_review.html", _base_context(
        ended_rounds=ended_rounds,
        selected_round=selected_round,
        review=review,
        reviews=reviews,
        form=form,
    ))


@student_required
def student_messages(request):
    internal_messages = list(
        InternalMessage.objects.filter(recipient=request.student, recalled_at__isnull=True).select_related("sender")[:100]
    )
    return render(request, "student/messages.html", _base_context(
        internal_messages=internal_messages,
        unread_message_count=sum(1 for item in internal_messages if item.read_at is None),
    ))


@student_required
@require_POST
def student_message_read(request, message_id):
    item = get_object_or_404(InternalMessage, pk=message_id, recipient=request.student, recalled_at__isnull=True)
    if item.read_at is None:
        item.read_at = timezone.now()
        item.save(update_fields=["read_at", "updated_at"])
    return _redirect_back(request, "student_messages")


@student_required
def student_hr_tasks(request):
    """로그인 수강생에게 배정된 역량 과제와 단계별 진행률을 보여준다."""
    student = request.student
    tasks = list(
        HRTask.objects.filter(assignee=student)
        .select_related("evaluation_round")
        .prefetch_related("required_skills__skill", "steps")
        .order_by("status", "due_date", "-created_at")
    )
    for task in tasks:
        task.skill_items = list(task.required_skills.all())
        task.step_items = list(task.steps.all())
        task.submission_obj = HRTaskSubmission.objects.filter(task=task, student=student).first()
        task.evaluation_obj = HRTaskEvaluation.objects.filter(task=task, student=student).first()

    stats = {
        "total": len(tasks),
        "active": sum(1 for task in tasks if task.status == HRTask.Status.IN_PROGRESS),
        "review": sum(1 for task in tasks if task.status == HRTask.Status.REVIEW),
        "overdue": sum(1 for task in tasks if task.is_overdue),
    }
    return render(
        request,
        "student/hr_tasks.html",
        _base_context(tasks=tasks, task_stats=stats),
    )


@student_required
@require_POST
@transaction.atomic
def student_hr_task_step_toggle(request, task_id, step_id):
    """담당 수강생의 Step 체크는 자기진도 표시일 뿐 최종 완료 판정이 아니다."""
    task = get_object_or_404(HRTask, pk=task_id, assignee=request.student)
    step = get_object_or_404(HRTaskStep, pk=step_id, task=task)

    if task.status in {HRTask.Status.REVIEW, HRTask.Status.COMPLETED}:
        messages.error(request, "검토 요청 또는 완료 상태의 과제는 Step을 수정할 수 없습니다.")
        return redirect("student_hr_tasks")

    step.is_completed = not step.is_completed
    step.completed_at = timezone.now() if step.is_completed else None
    step.save(update_fields=["is_completed", "completed_at", "updated_at"])

    if step.is_completed and task.status in {HRTask.Status.UNASSIGNED, HRTask.Status.SCHEDULED}:
        task.status = HRTask.Status.IN_PROGRESS
        task.save(update_fields=["status", "updated_at"])

    return redirect("student_hr_tasks")


@student_required
@require_POST
@transaction.atomic
def student_hr_task_submit(request, task_id):
    """Step 체크 여부와 관계없이 담당 수강생이 결과물을 제출해 튜터 검토를 요청한다."""
    student = request.student
    task = get_object_or_404(HRTask.objects.prefetch_related("steps"), pk=task_id, assignee=student)

    if task.status == HRTask.Status.COMPLETED:
        messages.error(request, "이미 완료 처리된 과제입니다.")
        return redirect("student_hr_tasks")

    content = (request.POST.get("content") or "").strip()
    attachment = request.FILES.get("attachment")
    if not content and not attachment:
        messages.error(request, "제출 내용 또는 첨부파일 중 하나는 입력해주세요.")
        return redirect("student_hr_tasks")

    submission, _ = HRTaskSubmission.objects.get_or_create(
        task=task,
        defaults={"student": student},
    )
    submission.student = student
    submission.content = content
    if attachment:
        submission.attachment = attachment
    submission.submitted_at = timezone.now()
    submission.save()

    task.status = HRTask.Status.REVIEW
    task.save(update_fields=["status", "updated_at"])
    messages.success(request, "과제를 제출했습니다. Step 체크는 자기진도 기록이며 최종 완료는 튜터 평가 후 확정됩니다.")
    return redirect("student_hr_tasks")
