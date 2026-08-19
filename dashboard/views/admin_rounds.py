from .common import *

@admin_required
def admin_round_detail(request, round_id):
    """회차 하나를 중심으로 과제, 팀 배정, 제출물, 관리자 코멘트를 통합 조회한다."""
    _sync_round_statuses()
    evaluation_round = get_object_or_404(EvaluationRound, pk=round_id)
    assignments = list(
        Assignment.objects.filter(evaluation_round=evaluation_round)
        .prefetch_related("required_skills__skill")
        .order_by("assignment_type", "id")
    )
    for item in assignments:
        item.skill_items = list(item.required_skills.all())
    team_assignment = next((item for item in assignments if item.assignment_type == Assignment.AssignmentType.TEAM), None)
    individual_assignment = next((item for item in assignments if item.assignment_type == Assignment.AssignmentType.INDIVIDUAL), None)
    assignment = team_assignment or individual_assignment

    teams = list(
        Team.objects.filter(evaluation_round=evaluation_round, is_active=True)
        .prefetch_related("memberships__student__user")
        .order_by("name")
    )
    submissions = {}
    if team_assignment:
        submissions = {
            item.team_id: item
            for item in TeamAssignmentSubmission.objects.filter(assignment=team_assignment)
            .select_related("team", "submitted_by__user", "commented_by")
        }

    individual_submissions = {}
    if individual_assignment:
        individual_submissions = {
            item.student_id: item
            for item in StudentAssignmentSubmission.objects.filter(assignment=individual_assignment)
            .select_related("student__user")
        }

    team_rows = []
    assigned_student_ids = set()
    for team in teams:
        memberships = list(team.memberships.all())
        memberships.sort(key=lambda m: (not m.is_leader, m.student.name))
        assigned_student_ids.update(m.student_id for m in memberships)
        team_rows.append({
            "team": team,
            "memberships": memberships,
            "submission": submissions.get(team.id),
        })

    active_students = list(
        Student.objects.filter(is_active=True, user__is_active=True)
        .select_related("user")
        .order_by("user__first_name", "user__username")
    )
    active_student_count = len(active_students)
    individual_rows = [
        {"student": student, "submission": individual_submissions.get(student.id)}
        for student in active_students
    ]
    team_template_count = evaluation_round.evaluation_templates.filter(
        is_active=True, evaluation_type=EvaluationTemplate.EvaluationType.TEAM
    ).count()
    personal_template_count = evaluation_round.evaluation_templates.filter(
        is_active=True, evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL
    ).count()
    team_submitted_count = len(submissions)
    individual_submitted_count = len(individual_submissions)
    stats = {
        "teams": len(teams),
        "assigned": len(assigned_student_ids),
        "unassigned": max(active_student_count - len(assigned_student_ids), 0),
        "team_submitted": team_submitted_count,
        "team_missing": max(len(teams) - team_submitted_count, 0) if team_assignment else 0,
        "individual_submitted": individual_submitted_count,
        "individual_missing": max(active_student_count - individual_submitted_count, 0) if individual_assignment else 0,
    }
    ready_checks = {
        "assignment": bool(assignments),
        "teams": bool(teams),
        "team_template": team_template_count > 0,
        "personal_template": personal_template_count > 0,
    }
    ready_percent = int(sum(ready_checks.values()) / 4 * 100)
    can_round_start = evaluation_round.status == EvaluationRound.Status.SCHEDULED
    can_assignment_manage = evaluation_round.status in {EvaluationRound.Status.SCHEDULED, EvaluationRound.Status.IN_PROGRESS} and not evaluation_round.evaluation_started
    can_evaluation_start = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and not evaluation_round.evaluation_started and ready_percent == 100
    can_pause = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started and not evaluation_round.is_locked
    can_resume = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started and evaluation_round.is_locked
    can_end = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started
    can_template_apply = evaluation_round.status != EvaluationRound.Status.ENDED and not evaluation_round.evaluation_started

    # 템플릿 관리 화면에서 만든 템플릿을 회차에 복사 적용할 수 있도록 목록을 제공한다.
    # 공용 원본 템플릿(evaluation_round가 없는 템플릿)만 선택지에 노출한다.
    team_template_options = list(
        EvaluationTemplate.objects.filter(
            is_active=True,
            evaluation_round__isnull=True,
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
        ).prefetch_related("criteria").order_by("name", "id")
    )
    personal_template_options = list(
        EvaluationTemplate.objects.filter(
            is_active=True,
            evaluation_round__isnull=True,
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
        ).prefetch_related("criteria").order_by("name", "id")
    )
    applied_team_template = evaluation_round.evaluation_templates.filter(
        is_active=True, evaluation_type=EvaluationTemplate.EvaluationType.TEAM
    ).first()
    applied_personal_template = evaluation_round.evaluation_templates.filter(
        is_active=True, evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL
    ).first()

    return render(request, "admin_ui/round_detail.html", _base_context(
        evaluation_round=evaluation_round, assignment=assignment, assignments=assignments, team_assignment=team_assignment,
        individual_assignment=individual_assignment, team_rows=team_rows, individual_rows=individual_rows,
        stats=stats, ready_checks=ready_checks, ready_percent=ready_percent,
        team_template_count=team_template_count, personal_template_count=personal_template_count,
        can_round_start=can_round_start, can_assignment_manage=can_assignment_manage,
        can_evaluation_start=can_evaluation_start, can_pause=can_pause, can_resume=can_resume, can_end=can_end,
        can_template_apply=can_template_apply, team_template_options=team_template_options,
        personal_template_options=personal_template_options,
        applied_team_template=applied_team_template, applied_personal_template=applied_personal_template,
    ))

@admin_required
@require_POST
@transaction.atomic
def admin_round_apply_templates(request, round_id):
    """기존 평가 템플릿을 선택한 회차 전용 템플릿으로 복사 적용한다."""
    evaluation_round = get_object_or_404(EvaluationRound, pk=round_id)
    if evaluation_round.status == EvaluationRound.Status.ENDED or evaluation_round.evaluation_started:
        messages.error(request, "평가가 시작되었거나 종료된 회차의 템플릿은 변경할 수 없습니다.")
        return redirect("admin_round_detail", round_id=evaluation_round.id)

    selections = [
        ("team_template_id", EvaluationTemplate.EvaluationType.TEAM, "팀 평가"),
        ("personal_template_id", EvaluationTemplate.EvaluationType.PERSONAL, "개인 평가"),
    ]
    applied = []

    for field_name, evaluation_type, label in selections:
        raw_id = request.POST.get(field_name, "").strip()
        if not raw_id:
            continue
        source = get_object_or_404(
            EvaluationTemplate.objects.prefetch_related("criteria"),
            pk=raw_id,
            evaluation_type=evaluation_type,
            evaluation_round__isnull=True,
            is_active=True,
        )
        # 같은 회차에 이미 적용된 템플릿을 다시 선택해도 안전하도록 삭제 전에 원본을 스냅샷한다.
        source_name = source.name
        criterion_rows = [
            {
                "title": criterion.title,
                "description": criterion.description,
                "order": criterion.order,
                "max_score": criterion.max_score,
                "is_required": criterion.is_required,
            }
            for criterion in source.criteria.all().order_by("order", "id")
        ]

        # 평가 시작 전이므로 기존 회차 전용 동일 유형 템플릿은 교체해도 안전하다.
        EvaluationTemplate.objects.filter(
            evaluation_round=evaluation_round,
            evaluation_type=evaluation_type,
        ).delete()

        copied = EvaluationTemplate.objects.create(
            name=source_name,
            evaluation_type=evaluation_type,
            evaluation_round=evaluation_round,
            is_active=True,
        )
        EvaluationCriterion.objects.bulk_create([
            EvaluationCriterion(template=copied, **row) for row in criterion_rows
        ])
        applied.append(label)

    if applied:
        messages.success(request, f"{', '.join(applied)} 템플릿을 이 회차에 적용했습니다.")
    else:
        messages.warning(request, "적용할 템플릿을 하나 이상 선택해 주세요.")
    return redirect("admin_round_detail", round_id=evaluation_round.id)

@admin_required
@require_POST
def admin_submission_comment(request, submission_id):
    submission = get_object_or_404(
        TeamAssignmentSubmission.objects.select_related("assignment__evaluation_round", "team"),
        pk=submission_id,
    )
    submission.admin_comment = request.POST.get("admin_comment", "").strip()
    submission.commented_by = request.user if submission.admin_comment else None
    submission.commented_at = timezone.now() if submission.admin_comment else None
    submission.save(update_fields=["admin_comment", "commented_by", "commented_at", "updated_at"])
    if submission.admin_comment:
        messages.success(request, f"{submission.team.name} 제출물에 관리자 코멘트를 저장했습니다.")
    else:
        messages.success(request, f"{submission.team.name} 제출물의 관리자 코멘트를 삭제했습니다.")
    return redirect("admin_round_detail", round_id=submission.assignment.evaluation_round_id)

@admin_required
def admin_rounds(request):
    _sync_round_statuses()
    rounds = list(EvaluationRound.objects.all())
    for evaluation_round in rounds:
        evaluation_round.status_display = evaluation_round.get_status_display()
        evaluation_round.assignment_title = " / ".join(evaluation_round.assignments.values_list("title", flat=True))
        evaluation_round.can_edit = evaluation_round.status == EvaluationRound.Status.SCHEDULED
        evaluation_round.can_delete = True
        evaluation_round.can_round_start = evaluation_round.status == EvaluationRound.Status.SCHEDULED
        evaluation_round.can_evaluation_start = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and not evaluation_round.evaluation_started
        evaluation_round.can_end = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started
        evaluation_round.can_reopen = evaluation_round.status == EvaluationRound.Status.ENDED
        evaluation_round.can_lock = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started and not evaluation_round.is_locked
        evaluation_round.can_unlock = evaluation_round.status == EvaluationRound.Status.IN_PROGRESS and evaluation_round.evaluation_started and evaluation_round.is_locked
        evaluation_round.is_selected_current = evaluation_round.is_current

    current_round = next((r for r in rounds if r.is_current), None)
    stats = {
        "total": len(rounds),
        "scheduled": sum(r.status == EvaluationRound.Status.SCHEDULED for r in rounds),
        "active": sum(r.status == EvaluationRound.Status.IN_PROGRESS for r in rounds),
        "ended": sum(r.status == EvaluationRound.Status.ENDED for r in rounds),
    }
    return render(request, "admin_ui/rounds.html", _base_context(rounds=rounds, stats=stats, current_round=current_round))

@admin_required
@require_POST
@transaction.atomic
def admin_round_create(request):
    if request.method != "POST":
        return _redirect_back(request, "admin_rounds")
    form = EvaluationRoundForm(request.POST)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return _redirect_back(request, "admin_rounds")
    evaluation_round = form.save(commit=False)
    evaluation_round.status = EvaluationRound.Status.SCHEDULED
    evaluation_round.evaluation_started = False
    evaluation_round.save()
    messages.success(request, f"{evaluation_round.name} 회차를 생성했습니다.")
    return _redirect_back(request, "admin_rounds")

@admin_required
@require_POST
@transaction.atomic
def admin_round_update(request, round_id):
    evaluation_round = get_object_or_404(EvaluationRound, pk=round_id)
    _sync_round_statuses()
    evaluation_round.refresh_from_db()
    if evaluation_round.status != EvaluationRound.Status.SCHEDULED:
        messages.error(request, "시작된 평가 회차는 기간과 회차명을 수정할 수 없습니다.")
        return _redirect_back(request, "admin_rounds")
    if request.method != "POST":
        return _redirect_back(request, "admin_rounds")
    form = EvaluationRoundForm(request.POST, instance=evaluation_round)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return _redirect_back(request, "admin_rounds")
    evaluation_round = form.save(commit=False)
    evaluation_round.status = EvaluationRound.Status.SCHEDULED
    evaluation_round.evaluation_started = False
    evaluation_round.save()
    messages.success(request, f"{evaluation_round.name} 회차를 수정했습니다.")
    return _redirect_back(request, "admin_rounds")

@admin_required
@require_POST
@transaction.atomic
def admin_round_delete(request, round_id):
    """회차와 연결 데이터를 안전하게 실제 삭제한다."""
    evaluation_round = get_object_or_404(EvaluationRound, pk=round_id)
    name = evaluation_round.name
    was_current = evaluation_round.is_current

    # 평가 점수의 criterion FK가 PROTECT이므로 회차 템플릿이 삭제되기 전에
    # 해당 회차 평가 점수 행을 먼저 지워야 회차 CASCADE 삭제가 막히지 않는다.
    TeamEvaluationScore.objects.filter(
        evaluation__evaluation_round=evaluation_round
    ).delete()
    PersonalEvaluationScore.objects.filter(
        evaluation__evaluation_round=evaluation_round
    ).delete()

    deleted_count, _ = EvaluationRound.objects.filter(pk=evaluation_round.pk).delete()
    if deleted_count <= 0 or EvaluationRound.objects.filter(pk=round_id).exists():
        messages.error(request, f"{name} 회차 삭제에 실패했습니다. 다시 시도해주세요.")
        return _redirect_back(request, "admin_rounds")

    # 현재 회차를 지웠다면 남은 진행중 회차 → 최신 회차 순으로 하나를 자동 지정한다.
    if was_current:
        replacement = (
            EvaluationRound.objects.filter(status=EvaluationRound.Status.IN_PROGRESS)
            .order_by("-start_at")
            .first()
            or EvaluationRound.objects.order_by("-start_at").first()
        )
        if replacement:
            EvaluationRound.objects.filter(pk=replacement.pk).update(is_current=True)

    messages.success(request, f"{name} 회차와 연결 데이터를 삭제했습니다.")
    return _redirect_back(request, "admin_rounds")

@admin_required
@require_POST
@transaction.atomic
def admin_round_action(request, round_id, action):
    evaluation_round = get_object_or_404(EvaluationRound, pk=round_id)
    now = timezone.now()

    if action == "set_current":
        EvaluationRound.objects.filter(is_current=True).exclude(pk=evaluation_round.pk).update(is_current=False)
        if not evaluation_round.is_current:
            evaluation_round.is_current = True
            evaluation_round.save(update_fields=["is_current", "updated_at"])
        messages.success(request, f"{evaluation_round.name}을(를) 현재 회차로 지정했습니다.")
        return _redirect_back(request, "admin_rounds")

    if action in {"start", "round_start"}:
        if evaluation_round.status != EvaluationRound.Status.SCHEDULED:
            messages.error(request, "예정 상태의 회차만 시작할 수 있습니다.")
            return _redirect_back(request, "admin_rounds")
        evaluation_round.status = EvaluationRound.Status.IN_PROGRESS
        evaluation_round.evaluation_started = False
        evaluation_round.is_locked = False
        if evaluation_round.start_at > now:
            evaluation_round.start_at = now
        messages.success(request, f"{evaluation_round.name} 회차를 시작했습니다. 평가 시작 전까지 과제 등록·수정과 학생 제출이 가능합니다.")

    elif action in {"evaluation_start", "eval_start"}:
        if evaluation_round.status != EvaluationRound.Status.IN_PROGRESS or evaluation_round.evaluation_started:
            messages.error(request, "진행 중이며 아직 평가를 시작하지 않은 회차에서만 평가를 시작할 수 있습니다.")
            return _redirect_back(request, "admin_rounds")

        assignment_exists = Assignment.objects.filter(evaluation_round=evaluation_round).exists()
        team_exists = Team.objects.filter(evaluation_round=evaluation_round, is_active=True).exists()
        team_template_exists = evaluation_round.evaluation_templates.filter(
            is_active=True, evaluation_type=EvaluationTemplate.EvaluationType.TEAM
        ).exists()
        personal_template_exists = evaluation_round.evaluation_templates.filter(
            is_active=True, evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL
        ).exists()
        missing = []
        if not assignment_exists:
            missing.append("과제")
        if not team_exists:
            missing.append("팀 편성")
        if not team_template_exists:
            missing.append("팀 평가 템플릿")
        if not personal_template_exists:
            missing.append("개인 평가 템플릿")
        if missing:
            messages.error(request, "평가 시작 전 준비가 필요합니다: " + ", ".join(missing))
            return _redirect_back(request, "admin_rounds")

        evaluation_round.evaluation_started = True
        evaluation_round.is_reopened = True
        evaluation_round.is_locked = False
        messages.success(request, f"{evaluation_round.name} 평가를 시작했습니다. 과제 등록·수정·제출은 이제 마감되고 평가 입력이 열립니다.")

    elif action in {"lock", "pause"}:
        if evaluation_round.status != EvaluationRound.Status.IN_PROGRESS or not evaluation_round.evaluation_started:
            messages.error(request, "평가가 시작된 진행 중 회차만 일시 중단할 수 있습니다.")
            return _redirect_back(request, "admin_rounds")
        if evaluation_round.is_locked:
            messages.info(request, f"{evaluation_round.name} 평가는 이미 중단된 상태입니다.")
            return _redirect_back(request, "admin_rounds")
        evaluation_round.is_locked = True
        messages.success(request, f"{evaluation_round.name} 평가를 일시 중단했습니다. 기존 임시저장·제출 데이터는 그대로 유지됩니다.")

    elif action in {"unlock", "resume"}:
        if evaluation_round.status != EvaluationRound.Status.IN_PROGRESS or not evaluation_round.evaluation_started:
            messages.error(request, "평가가 시작된 진행 중 회차만 재개할 수 있습니다.")
            return _redirect_back(request, "admin_rounds")
        if not evaluation_round.is_locked:
            messages.info(request, f"{evaluation_round.name} 평가는 이미 진행 중입니다.")
            return _redirect_back(request, "admin_rounds")
        evaluation_round.is_locked = False
        messages.success(request, f"{evaluation_round.name} 평가를 재개했습니다. 학생들이 다시 임시저장·제출할 수 있습니다.")

    elif action == "end":
        if evaluation_round.status != EvaluationRound.Status.IN_PROGRESS or not evaluation_round.evaluation_started:
            messages.error(request, "평가가 시작된 진행 중 회차만 종료할 수 있습니다.")
            return _redirect_back(request, "admin_rounds")
        evaluation_round.status = EvaluationRound.Status.ENDED
        evaluation_round.evaluation_started = False
        evaluation_round.is_reopened = False
        evaluation_round.is_locked = True
        if evaluation_round.end_at > now:
            evaluation_round.end_at = now
        messages.success(request, f"{evaluation_round.name} 평가를 종료했습니다.")

    elif action == "reopen":
        if evaluation_round.status != EvaluationRound.Status.ENDED:
            messages.error(request, "종료된 회차만 다시 열 수 있습니다.")
            return _redirect_back(request, "admin_rounds")
        evaluation_round.status = EvaluationRound.Status.IN_PROGRESS
        evaluation_round.evaluation_started = True
        evaluation_round.is_reopened = True
        evaluation_round.is_locked = False
        if evaluation_round.end_at <= now:
            evaluation_round.end_at = now + timedelta(days=1)
        messages.success(request, f"{evaluation_round.name} 평가를 다시 열었습니다.")
    else:
        messages.error(request, "지원하지 않는 회차 작업입니다.")
        return _redirect_back(request, "admin_rounds")

    evaluation_round.save()
    return _redirect_back(request, "admin_rounds")

def _assignment_skill_payload(request):
    skill_ids = request.POST.getlist("skill_id")
    weights = request.POST.getlist("skill_weight")
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

    existing_ids = set(Skill.objects.filter(id__in=[sid for sid, _ in parsed]).values_list("id", flat=True))
    if len(existing_ids) != len(parsed):
        errors.append("선택한 역량 중 존재하지 않는 항목이 있습니다.")

    return parsed, errors


def _save_assignment_skills(assignment, parsed):
    AssignmentSkill.objects.filter(assignment=assignment).delete()
    AssignmentSkill.objects.bulk_create([
        AssignmentSkill(assignment=assignment, skill_id=skill_id, weight=weight)
        for skill_id, weight in parsed
    ])


@admin_required
def admin_assignments(request):
    _sync_round_statuses()
    assignments = list(
        Assignment.objects.select_related("evaluation_round").prefetch_related("required_skills__skill").order_by("-evaluation_round__start_at")
    )
    for assignment in assignments:
        assignment.round_name = assignment.evaluation_round.name
        assignment.deadline = assignment.evaluation_round.end_at
        assignment.status_display = assignment.evaluation_round.get_status_display()
        assignment.can_edit = _assignment_editable(assignment)
        assignment.can_delete = assignment.can_edit
        assignment.skill_items = list(assignment.required_skills.all())
        assignment.skill_weight_total = sum(item.weight for item in assignment.skill_items)
        if assignment.attachment:
            assignment.attachment_url = assignment.attachment.url
            assignment.attachment_name = assignment.attachment.name.rsplit("/", 1)[-1]
        else:
            assignment.attachment_url = ""
            assignment.attachment_name = ""

    rounds = EvaluationRound.objects.filter(
        Q(status=EvaluationRound.Status.SCHEDULED) | Q(status=EvaluationRound.Status.IN_PROGRESS, evaluation_started=False)
    ).order_by("-start_at")
    return render(
        request,
        "admin_ui/assignments.html",
        _base_context(assignments=assignments, rounds=rounds, skills=Skill.objects.all()),
    )

@admin_required
@transaction.atomic
def admin_assignment_create(request):
    if request.method != "POST":
        return redirect(f"{reverse('admin_assignments')}?open=create")
    available_rounds = EvaluationRound.objects.filter(
        Q(status=EvaluationRound.Status.SCHEDULED) | Q(status=EvaluationRound.Status.IN_PROGRESS, evaluation_started=False)
    )
    form = AssignmentForm(request.POST, request.FILES, rounds=available_rounds)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return _redirect_back(request, "admin_assignments")
    evaluation_round = form.cleaned_data["evaluation_round"]
    if evaluation_round.status not in {EvaluationRound.Status.SCHEDULED, EvaluationRound.Status.IN_PROGRESS} or evaluation_round.evaluation_started:
        messages.error(request, "과제는 회차 시작 전부터 진행 중 평가 시작 전까지만 등록할 수 있습니다.")
        return _redirect_back(request, "admin_assignments")
    parsed_skills, skill_errors = _assignment_skill_payload(request)
    if skill_errors:
        for error in skill_errors:
            messages.error(request, error)
        return _redirect_back(request, "admin_assignments")
    assignment = form.save()
    _save_assignment_skills(assignment, parsed_skills)
    messages.success(request, f"{assignment.title} 과제를 등록했습니다.")
    return _redirect_back(request, "admin_assignments")

@admin_required
@transaction.atomic
def admin_assignment_update(request, assignment_id):
    assignment = get_object_or_404(Assignment.objects.select_related("evaluation_round"), pk=assignment_id)
    if request.method != "POST":
        return redirect(f"{reverse('admin_assignments')}?edit={assignment.id}")
    if not _assignment_editable(assignment):
        messages.error(request, "과제는 회차 시작 전부터 진행 중 평가 시작 전까지만 수정할 수 있습니다.")
        return _redirect_back(request, "admin_assignments")
    available_rounds = EvaluationRound.objects.filter(
        Q(status=EvaluationRound.Status.SCHEDULED) | Q(status=EvaluationRound.Status.IN_PROGRESS, evaluation_started=False)
    ).distinct()
    form = AssignmentForm(request.POST, request.FILES, instance=assignment, rounds=available_rounds)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return _redirect_back(request, "admin_assignments")
    target_round = form.cleaned_data["evaluation_round"]
    if target_round.status not in {EvaluationRound.Status.SCHEDULED, EvaluationRound.Status.IN_PROGRESS} or target_round.evaluation_started:
        messages.error(request, "과제는 회차 시작 전부터 진행 중 평가 시작 전 상태에서만 수정할 수 있습니다.")
        return _redirect_back(request, "admin_assignments")
    parsed_skills, skill_errors = _assignment_skill_payload(request)
    if skill_errors:
        for error in skill_errors:
            messages.error(request, error)
        return _redirect_back(request, "admin_assignments")
    assignment = form.save()
    _save_assignment_skills(assignment, parsed_skills)
    messages.success(request, f"{assignment.title} 과제를 수정했습니다.")
    return _redirect_back(request, "admin_assignments")

@admin_required
@require_POST
@transaction.atomic
def admin_assignment_delete(request, assignment_id):
    assignment = get_object_or_404(Assignment.objects.select_related("evaluation_round"), pk=assignment_id)
    if request.method != "POST":
        return _redirect_back(request, "admin_assignments")
    if not _assignment_editable(assignment):
        messages.error(request, "과제는 회차 시작 전부터 진행 중 평가 시작 전까지만 삭제할 수 있습니다.")
        return _redirect_back(request, "admin_assignments")
    title = assignment.title
    assignment.delete()
    messages.success(request, f"{title} 과제를 삭제했습니다.")
    return _redirect_back(request, "admin_assignments")
