"""Student profile, feedback, notification and messaging views."""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .common import (
    _active_announcements,
    _base_context,
    _display_round_for_student,
    _redirect_back,
    _student_progress,
    _student_team,
    student_required,
)
from ..forms import SelfProjectReviewForm, StudentProfileForm
from ..models import (
    AdminStudentComment,
    AnnouncementRead,
    EvaluationRound,
    HRTaskSkillUpdate,
    InternalMessage,
    PersonalEvaluation,
    ResultPublishSetting,
    SelfProjectReview,
    StudentResult,
    StudentSkill,
    TeamEvaluation,
    TeamMembership,
)


@student_required
def student_profile(request):
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
        password_form = (
            PasswordChangeForm(request.user)
            if request.user.has_usable_password()
            else SetPasswordForm(request.user)
        )

    now = timezone.now()
    round_ids = set(
        TeamMembership.objects.filter(student=student).values_list("team__evaluation_round_id", flat=True)
    )
    round_ids.update(
        TeamEvaluation.objects.filter(evaluator=student).values_list("evaluation_round_id", flat=True)
    )
    round_ids.update(
        PersonalEvaluation.objects.filter(evaluator=student).values_list("evaluation_round_id", flat=True)
    )
    round_ids.update(
        StudentResult.objects.filter(student=student).values_list("evaluation_round_id", flat=True)
    )

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
            publish_setting
            and (
                publish_setting.is_published
                or (publish_setting.publish_at and publish_setting.publish_at <= now)
            )
        )
        history.append(
            {
                "round": evaluation_round,
                "team": membership.team if membership else None,
                "team_submitted": team_qs.filter(is_submitted=True).count(),
                "team_saved": team_qs.filter(is_submitted=False).count(),
                "personal_submitted": personal_qs.filter(is_submitted=True).count(),
                "personal_saved": personal_qs.filter(is_submitted=False).count(),
                "result": result if result_published else None,
                "result_published": result_published,
            }
        )

    social_accounts = []
    try:
        for account in request.user.socialaccount_set.all():
            provider_name = {"google": "Google", "kakao": "Kakao"}.get(
                account.provider,
                account.provider.title(),
            )
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

    return render(
        request,
        "student/profile.html",
        _base_context(
            profile_form=profile_form,
            password_form=password_form,
            password_mode="change" if request.user.has_usable_password() else "set",
            history=history,
            social_accounts=social_accounts,
            current_round=current_round,
            current_team=current_team,
            skill_profiles=skill_profiles,
            recent_skill_updates=recent_skill_updates,
        ),
    )


@student_required
@require_POST
def student_announcement_read(request, announcement_id):
    announcement = get_object_or_404(_active_announcements(request.student), pk=announcement_id)
    AnnouncementRead.objects.get_or_create(student=request.student, announcement=announcement)
    return _redirect_back(request, "student_home")


@student_required
def student_feedback(request):
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
        [AnnouncementRead(student=request.student, announcement=item) for item in announcements if item.id not in read_ids],
        ignore_conflicts=True,
    )

    notices = []
    current_round = _display_round_for_student()
    if current_round:
        progress = _student_progress(
            request.student,
            current_round,
            _student_team(request.student, current_round),
        )
        now = timezone.now()
        if current_round.is_locked:
            notices.append(
                {
                    "level": "warning",
                    "icon": "bi-lock-fill",
                    "title": "평가가 일시 중단되었습니다.",
                    "body": f"{current_round.name} 회차는 관리자가 재개할 때까지 저장·제출할 수 없습니다.",
                    "url": "student_evaluation_status",
                }
            )
        elif current_round.status == EvaluationRound.Status.IN_PROGRESS:
            remain = current_round.end_at - now
            if timedelta(0) <= remain <= timedelta(days=2):
                hours = max(int(remain.total_seconds() // 3600), 0)
                notices.append(
                    {
                        "level": "danger",
                        "icon": "bi-alarm-fill",
                        "title": "평가 마감이 임박했습니다.",
                        "body": f"{current_round.name} 마감까지 약 {hours}시간 남았습니다.",
                        "url": "student_evaluation_status",
                    }
                )
            if progress["team_completed"] < progress["team_total"]:
                notices.append(
                    {
                        "level": "info",
                        "icon": "bi-people-fill",
                        "title": "완료하지 않은 팀 평가가 있습니다.",
                        "body": f"팀 평가 {progress['team_total'] - progress['team_completed']}건이 남아 있습니다.",
                        "url": "student_team_evaluation",
                    }
                )
            elif progress["personal_completed"] < progress["personal_total"]:
                notices.append(
                    {
                        "level": "info",
                        "icon": "bi-person-check-fill",
                        "title": "완료하지 않은 개인 평가가 있습니다.",
                        "body": f"개인 평가 {progress['personal_total'] - progress['personal_completed']}건이 남아 있습니다.",
                        "url": "student_personal_evaluation",
                    }
                )

        publish_setting = ResultPublishSetting.objects.filter(evaluation_round=current_round).first()
        if (
            publish_setting
            and publish_setting.is_published
            and (not publish_setting.publish_at or publish_setting.publish_at <= now)
        ):
            notices.append(
                {
                    "level": "success",
                    "icon": "bi-bar-chart-fill",
                    "title": "평가 결과가 공개되었습니다.",
                    "body": f"{current_round.name} 결과를 확인할 수 있습니다.",
                    "url": "student_results",
                }
            )

    return render(
        request,
        "student/notifications.html",
        _base_context(announcements=announcements, notices=notices, current_round=current_round),
    )


@student_required
def student_self_review(request):
    ended_rounds = list(
        EvaluationRound.objects.filter(
            status=EvaluationRound.Status.ENDED,
            teams__memberships__student=request.student,
        )
        .distinct()
        .order_by("-start_at")
    )

    selected_round = None
    raw_round_id = (
        request.POST.get("evaluation_round_id")
        or request.GET.get("round")
        or ""
    ).strip()
    if raw_round_id:
        selected_round = next(
            (round_obj for round_obj in ended_rounds if str(round_obj.id) == raw_round_id),
            None,
        )
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

    return render(
        request,
        "student/self_review.html",
        _base_context(
            ended_rounds=ended_rounds,
            selected_round=selected_round,
            review=review,
            reviews=reviews,
            form=form,
        ),
    )


@student_required
def student_messages(request):
    internal_messages = list(
        InternalMessage.objects.filter(
            recipient=request.student,
            recalled_at__isnull=True,
        ).select_related("sender")[:100]
    )
    return render(
        request,
        "student/messages.html",
        _base_context(
            internal_messages=internal_messages,
            unread_message_count=sum(1 for item in internal_messages if item.read_at is None),
        ),
    )


@student_required
@require_POST
def student_message_read(request, message_id):
    item = get_object_or_404(
        InternalMessage,
        pk=message_id,
        recipient=request.student,
        recalled_at__isnull=True,
    )
    if item.read_at is None:
        item.read_at = timezone.now()
        item.save(update_fields=["read_at", "updated_at"])
    return _redirect_back(request, "student_messages")
