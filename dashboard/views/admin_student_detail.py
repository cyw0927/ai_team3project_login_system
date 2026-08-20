from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .common import _base_context, _current_round, admin_required
from .admin_skills import _sync_skill_to_students
from ..models import (
    AdminStudentComment,
    EvaluationRound,
    PersonalEvaluation,
    SelfProjectReview,
    Skill,
    Student,
    StudentResult,
    StudentSkill,
    Team,
    TeamEvaluation,
    TeamMembership,
)


@admin_required
def admin_student_detail(request, student_id):
    student = get_object_or_404(Student.objects.select_related("user"), pk=student_id)
    current_round = _current_round()
    current_team = None
    if current_round:
        membership = (
            TeamMembership.objects.filter(student=student, team__evaluation_round=current_round)
            .select_related("team")
            .first()
        )
        current_team = membership.team if membership else None

    memberships = list(
        TeamMembership.objects.filter(student=student)
        .select_related("team", "team__evaluation_round")
        .order_by("-team__evaluation_round__start_at")
    )
    results = list(
        StudentResult.objects.filter(student=student)
        .select_related("evaluation_round")
        .order_by("-evaluation_round__start_at")
    )

    team_required = personal_required = 0
    team_submitted = personal_submitted = 0
    team_saved = personal_saved = 0
    if current_round:
        if current_team:
            team_required = Team.objects.filter(
                evaluation_round=current_round,
                is_active=True,
            ).exclude(pk=current_team.pk).count()
            personal_required = TeamMembership.objects.filter(
                team=current_team,
            ).exclude(student=student).count()
        team_qs = TeamEvaluation.objects.filter(
            evaluation_round=current_round,
            evaluator=student,
        )
        personal_qs = PersonalEvaluation.objects.filter(
            evaluation_round=current_round,
            evaluator=student,
        )
        team_submitted = team_qs.filter(is_submitted=True).count()
        personal_submitted = personal_qs.filter(is_submitted=True).count()
        team_saved = team_qs.filter(is_submitted=False).count()
        personal_saved = personal_qs.filter(is_submitted=False).count()

    required_total = team_required + personal_required
    submitted_total = team_submitted + personal_submitted
    completion_percent = round((submitted_total / required_total) * 100) if required_total else 0

    social_accounts = []
    try:
        for account in student.user.socialaccount_set.all():
            provider_name = {"google": "Google", "kakao": "Kakao"}.get(
                account.provider,
                account.provider.title(),
            )
            social_accounts.append({"provider": account.provider, "name": provider_name})
    except Exception:
        social_accounts = []

    activities = []
    for evaluation in (
        TeamEvaluation.objects.filter(evaluator=student)
        .select_related("target_team", "evaluation_round")
        .order_by("-updated_at")[:8]
    ):
        activities.append({
            "at": evaluation.updated_at,
            "icon": "bi-people",
            "title": f"{evaluation.target_team.name} 팀 평가",
            "detail": f"{evaluation.evaluation_round.name} · {'제출 완료' if evaluation.is_submitted else '임시 저장'}",
        })
    for evaluation in (
        PersonalEvaluation.objects.filter(evaluator=student)
        .select_related("target_student__user", "evaluation_round")
        .order_by("-updated_at")[:8]
    ):
        activities.append({
            "at": evaluation.updated_at,
            "icon": "bi-person-check",
            "title": f"{evaluation.target_student.name} 개인 평가",
            "detail": f"{evaluation.evaluation_round.name} · {'제출 완료' if evaluation.is_submitted else '임시 저장'}",
        })
    activities = sorted(activities, key=lambda item: item["at"], reverse=True)[:8]

    admin_comments = list(
        AdminStudentComment.objects.filter(student=student)
        .select_related("evaluation_round", "created_by")
        .order_by("-evaluation_round__start_at", "-updated_at")
    )
    comment_rounds = list(EvaluationRound.objects.order_by("-start_at"))
    self_reviews = list(
        SelfProjectReview.objects.filter(student=student)
        .select_related("evaluation_round")
        .order_by("-evaluation_round__start_at")
    )
    skill_profiles = list(
        StudentSkill.objects.filter(student=student)
        .select_related("skill")
        .order_by("-score", "skill__name")
    )

    return render(request, "admin_ui/student_detail.html", _base_context(
        student=student,
        current_round=current_round,
        current_team=current_team,
        memberships=memberships,
        results=results,
        social_accounts=social_accounts,
        activities=activities,
        admin_comments=admin_comments,
        comment_rounds=comment_rounds,
        self_reviews=self_reviews,
        skill_profiles=skill_profiles,
        eval_stats={
            "team_required": team_required,
            "team_submitted": team_submitted,
            "team_saved": team_saved,
            "personal_required": personal_required,
            "personal_submitted": personal_submitted,
            "personal_saved": personal_saved,
            "required_total": required_total,
            "submitted_total": submitted_total,
            "completion_percent": completion_percent,
        },
    ))


@admin_required
@require_POST
@transaction.atomic
def admin_student_skill_save(request, student_id):
    student = get_object_or_404(Student.objects.select_related("user"), pk=student_id)
    skill_name = (request.POST.get("skill_name") or "").strip()
    raw_score = (request.POST.get("score") or "").strip()
    note = (request.POST.get("note") or "").strip()

    if not skill_name:
        messages.error(request, "역량 이름을 입력해주세요.")
        return redirect("admin_student_detail", student_id=student.id)
    if len(skill_name) > 80:
        messages.error(request, "역량 이름은 80자 이하로 입력해주세요.")
        return redirect("admin_student_detail", student_id=student.id)

    try:
        score = int(raw_score)
    except (TypeError, ValueError):
        score = -1
    if not 0 <= score <= 100:
        messages.error(request, "역량 점수는 0~100 사이로 입력해주세요.")
        return redirect("admin_student_detail", student_id=student.id)
    if len(note) > 300:
        messages.error(request, "역량 메모는 300자 이하로 입력해주세요.")
        return redirect("admin_student_detail", student_id=student.id)

    skill, skill_created = Skill.objects.get_or_create(name=skill_name)
    if skill_created:
        _sync_skill_to_students(skill)
    _, created = StudentSkill.objects.update_or_create(
        student=student,
        skill=skill,
        defaults={"score": score, "note": note},
    )
    action = "추가" if created else "수정"
    messages.success(request, f"{skill.name} 역량을 {score}점으로 {action}했습니다.")
    return redirect("admin_student_detail", student_id=student.id)


@admin_required
@require_POST
@transaction.atomic
def admin_student_skill_delete(request, student_id, profile_id):
    student = get_object_or_404(Student, pk=student_id)
    profile = get_object_or_404(
        StudentSkill.objects.select_related("skill"),
        pk=profile_id,
        student=student,
    )
    skill_name = profile.skill.name
    profile.delete()
    messages.success(request, f"{skill_name} 역량을 프로필에서 제거했습니다.")
    return redirect("admin_student_detail", student_id=student.id)


@admin_required
@require_POST
@transaction.atomic
def admin_student_comment_save(request, student_id):
    student = get_object_or_404(Student.objects.select_related("user"), pk=student_id)
    round_id = (request.POST.get("evaluation_round_id") or "").strip()
    comment = (request.POST.get("comment") or "").strip()

    if not round_id:
        messages.error(request, "피드백을 남길 평가 회차를 선택해주세요.")
        return redirect("admin_student_detail", student_id=student.id)
    evaluation_round = get_object_or_404(EvaluationRound, pk=round_id)
    if not comment:
        messages.error(request, "학생에게 전달할 피드백 내용을 입력해주세요.")
        return redirect("admin_student_detail", student_id=student.id)
    if len(comment) > 2000:
        messages.error(request, "관리자 피드백은 2,000자 이하로 입력해주세요.")
        return redirect("admin_student_detail", student_id=student.id)

    _, created = AdminStudentComment.objects.update_or_create(
        evaluation_round=evaluation_round,
        student=student,
        defaults={
            "comment": comment,
            "created_by": request.user,
            "read_at": None,
        },
    )
    action = "등록" if created else "수정"
    messages.success(request, f"{student.name} 학생의 {evaluation_round.name} 피드백을 {action}했습니다.")
    return redirect("admin_student_detail", student_id=student.id)


@admin_required
@require_POST
@transaction.atomic
def admin_student_comment_delete(request, student_id, comment_id):
    student = get_object_or_404(Student, pk=student_id)
    feedback = get_object_or_404(AdminStudentComment, pk=comment_id, student=student)
    round_name = feedback.evaluation_round.name
    feedback.delete()
    messages.success(request, f"{student.name} 학생의 {round_name} 관리자 피드백을 삭제했습니다.")
    return redirect("admin_student_detail", student_id=student.id)
