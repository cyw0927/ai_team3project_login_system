import math
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
import random
import secrets
import string
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.sessions.models import Session
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q
from django.http import HttpResponse, FileResponse, Http404
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from ..forms import AssignmentForm, EvaluationCriterionForm, EvaluationRoundForm, EvaluationTemplateForm, StudentCreateForm, StudentUpdateForm, StudentProfileForm, SelfProjectReviewForm, TeamForm
from ..models import (
    Assignment, EvaluationCriterion, EvaluationRound, EvaluationTemplate,
    PersonalEvaluation, PersonalEvaluationScore, Student, StudentResult, Team,
    TeamEvaluation, TeamEvaluationScore, TeamMembership, TeamResult,
    ResultPublishSetting, Announcement, AnnouncementRead, InternalMessage, AdminActivityLog, RoundAttendance,
    TeamAssignmentSubmission, StudentAssignmentSubmission, AdminStudentComment, SelfProjectReview, StudentBadge,
    Skill, StudentSkill, AssignmentSkill, AssignmentSkillImpact, HRTask, HRTaskStep, HRTaskSkill, HRTaskSubmission, HRTaskEvaluation, HRTaskSkillUpdate,
)

def _base_context(**extra):
    """공통 템플릿 컨텍스트. 각 화면에서 ORM 조회 결과를 추가한다."""
    today = timezone.localdate()

    # 관리자 사이드바의 역량과제 알림을 한 번의 집계 쿼리로 계산한다.
    growth_counts = HRTask.objects.aggregate(
        review=Count(
            "id",
            filter=Q(status=HRTask.Status.REVIEW),
        ),
        overdue=Count(
            "id",
            filter=Q(due_date__lt=today) & ~Q(status=HRTask.Status.COMPLETED),
        ),
        attention=Count(
            "id",
            filter=(
                Q(status=HRTask.Status.REVIEW)
                | (Q(due_date__lt=today) & ~Q(status=HRTask.Status.COMPLETED))
            ),
        ),
    )
    growth_review_count = growth_counts["review"]
    growth_overdue_count = growth_counts["overdue"]
    growth_attention_count = growth_counts["attention"]

    context = {
        "score_choices": range(1, 6),
        "stats": {},
        "progress": {},
        "growth_review_count": growth_review_count,
        "growth_overdue_count": growth_overdue_count,
        "growth_attention_count": growth_attention_count,
    }
    context.update(extra)
    return context

def _default_destination(user):
    """로그인한 사용자의 역할에 따라 기본 화면을 결정한다."""
    if user.is_staff or user.is_superuser:
        return "admin_dashboard"
    return "student_home"

def _redirect_back(request, fallback):
    """POST 작업 후 사용자가 작업하던 화면/탭/검색 조건으로 돌아간다."""
    candidate = (
        request.POST.get("next")
        or request.GET.get("next")
        or request.META.get("HTTP_REFERER")
        or ""
    ).strip()

    if candidate and url_has_allowed_host_and_scheme(
        url=candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(candidate)
    return redirect(fallback)

def student_required(view_func):
    """활성 수강생만 학생 화면에 접근하도록 제한한다."""
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if request.user.is_staff or request.user.is_superuser:
            return redirect("admin_dashboard")

        profile = getattr(request.user, "student_profile", None)
        if profile and profile.is_active:
            request.student = profile
            return view_func(request, *args, **kwargs)

        messages.error(request, "활성 수강생 계정만 이용할 수 있습니다.")
        logout(request)
        return redirect("login")

    return wrapped

def admin_required(view_func):
    """관리자 권한이 있는 계정만 관리자 화면에 접근하도록 제한한다."""
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if request.user.is_staff or request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        messages.error(request, "관리자 권한이 필요한 페이지입니다.")
        return redirect("student_home")

    return wrapped

def _social_login_context():
    google_ready = bool(
        settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET
    )
    kakao_ready = bool(
        settings.KAKAO_REST_API_KEY and settings.KAKAO_CLIENT_SECRET
    )
    return {
        "google_oauth_configured": google_ready,
        "kakao_oauth_configured": kakao_ready,
        # 구버전 템플릿 호환 alias
        "google_login_available": google_ready,
        "kakao_login_available": kakao_ready,
    }

def _display_round_for_student():
    """학생 화면에서 보여줄 회차: 진행 중 > 예정 > 최근 종료 순."""
    _sync_round_statuses()
    now = timezone.now()
    return (
        EvaluationRound.objects.filter(
            status=EvaluationRound.Status.IN_PROGRESS,
            evaluation_started=True,
            start_at__lte=now,
            end_at__gte=now,
        ).order_by("-start_at").first()
        or EvaluationRound.objects.filter(status=EvaluationRound.Status.IN_PROGRESS).order_by("-start_at").first()
        or EvaluationRound.objects.filter(status=EvaluationRound.Status.SCHEDULED).order_by("start_at").first()
        or EvaluationRound.objects.order_by("-start_at").first()
    )

def _decorate_assignment(assignment):
    if not assignment:
        return None
    assignment.deadline = assignment.evaluation_round.end_at
    assignment.start_at = assignment.evaluation_round.start_at
    assignment.status_display = assignment.evaluation_round.get_status_display()
    if assignment.attachment:
        assignment.attachment_url = assignment.attachment.url
        assignment.attachment_name = assignment.attachment.name.rsplit("/", 1)[-1]
    else:
        assignment.attachment_url = ""
        assignment.attachment_name = ""
    return assignment

def _attendance_for(student, evaluation_round):
    """출결 미등록 학생은 기본 출석으로 본다."""
    if not evaluation_round or not student:
        return None
    return RoundAttendance.objects.filter(
        evaluation_round=evaluation_round, student=student
    ).first()

def _is_absent_from_team_eval(student, evaluation_round):
    attendance = _attendance_for(student, evaluation_round)
    return bool(attendance and attendance.status in {RoundAttendance.Status.ABSENT, RoundAttendance.Status.EXCUSED})

def _student_progress(student, evaluation_round, my_team):
    if not evaluation_round:
        return {
            "team_completed": 0, "team_total": 0,
            "personal_completed": 0, "personal_total": 0,
            "overall_percent": 0,
        }

    absent_from_team_eval = _is_absent_from_team_eval(student, evaluation_round)
    team_total = 0 if absent_from_team_eval else (
        Team.objects.filter(evaluation_round=evaluation_round, is_active=True)
        .exclude(pk=getattr(my_team, "pk", None)).count() if my_team else 0
    )
    team_completed = TeamEvaluation.objects.filter(
        evaluation_round=evaluation_round, evaluator=student, is_submitted=True
    ).count()

    personal_total = 0
    if my_team:
        personal_total = TeamMembership.objects.filter(team=my_team).exclude(student=student).count()
    personal_completed = PersonalEvaluation.objects.filter(
        evaluation_round=evaluation_round, evaluator=student, is_submitted=True
    ).count()

    total = team_total + personal_total
    completed = min(team_completed, team_total) + min(personal_completed, personal_total)
    overall_percent = round((completed / total) * 100) if total else 0
    return {
        "team_completed": min(team_completed, team_total),
        "team_total": team_total,
        "personal_completed": min(personal_completed, personal_total),
        "personal_total": personal_total,
        "overall_percent": overall_percent,
    }

def _current_round_for_evaluation():
    """학생 평가 화면에 표시할 진행 중 회차. 잠금 여부와 무관하게 찾는다."""
    now = timezone.now()
    return (
        EvaluationRound.objects.filter(
            status=EvaluationRound.Status.IN_PROGRESS,
            evaluation_started=True,
            start_at__lte=now,
            end_at__gte=now,
        )
        .order_by("-start_at")
        .first()
        or EvaluationRound.objects.filter(
            status=EvaluationRound.Status.IN_PROGRESS,
            evaluation_started=True,
        ).order_by("-start_at").first()
    )

def _active_round_for_evaluation():
    """실제 평가 입력에 사용할, 잠기지 않은 진행 중 회차."""
    evaluation_round = _current_round_for_evaluation()
    if evaluation_round and not evaluation_round.is_locked:
        return evaluation_round
    return None

def _student_team(student, evaluation_round):
    membership = (
        TeamMembership.objects.filter(
            student=student,
            team__evaluation_round=evaluation_round,
            team__is_active=True,
        )
        .select_related("team")
        .first()
    )
    return membership.team if membership else None

def _template_for(evaluation_round, evaluation_type):
    """회차 전용 활성 템플릿을 우선하고, 없으면 공통 활성 템플릿을 사용한다."""
    return (
        EvaluationTemplate.objects.filter(
            evaluation_type=evaluation_type,
            is_active=True,
            evaluation_round=evaluation_round,
        )
        .prefetch_related("criteria")
        .first()
        or EvaluationTemplate.objects.filter(
            evaluation_type=evaluation_type,
            is_active=True,
            evaluation_round__isnull=True,
        )
        .prefetch_related("criteria")
        .first()
    )

def _criteria_complete(post_data, criteria):
    for criterion in criteria:
        if criterion.is_required and not post_data.get(f"criterion_{criterion.id}"):
            return False
    return True

def _save_scores(evaluation, score_model, criteria, post_data):
    """현재 폼 상태를 그대로 저장한다. 비워진 항목은 이전 저장값도 제거한다."""
    for criterion in criteria:
        raw_score = post_data.get(f"criterion_{criterion.id}")
        if not raw_score:
            score_model.objects.filter(evaluation=evaluation, criterion=criterion).delete()
            continue
        try:
            score = int(raw_score)
        except (TypeError, ValueError):
            score_model.objects.filter(evaluation=evaluation, criterion=criterion).delete()
            continue
        if score < 1 or score > min(5, criterion.max_score):
            score_model.objects.filter(evaluation=evaluation, criterion=criterion).delete()
            continue
        score_model.objects.update_or_create(
            evaluation=evaluation,
            criterion=criterion,
            defaults={"score": score},
        )

def _apply_assignment_skill_impacts(evaluation_round, result_rows):
    """종료 회차의 기본 과제 점수를 수강생 역량 프로필에 반영한다.

    조별과제는 해당 학생의 팀점수, 개별과제는 개인점수를 100점 환산해 사용한다.
    같은 회차에서 재계산되어도 기존 반영분을 먼저 제거한 뒤 다시 계산해 중복 누적을 막는다.
    """
    if evaluation_round.status != EvaluationRound.Status.ENDED:
        return

    assignments = list(
        Assignment.objects.filter(evaluation_round=evaluation_round)
        .prefetch_related("required_skills__skill")
        .order_by("id")
    )
    requirements = {
        assignment.id: list(assignment.required_skills.all())
        for assignment in assignments
    }
    if not any(requirements.values()):
        return

    assignment_ids = [assignment.id for assignment in assignments]
    for result in result_rows:
        # 이 회차 기본과제로 이미 반영된 값만 되돌린 기준점에서 다시 계산한다.
        old_impacts = list(
            AssignmentSkillImpact.objects.filter(
                assignment_id__in=assignment_ids,
                student=result.student,
            )
        )
        old_by_skill = {}
        for impact in old_impacts:
            old_by_skill.setdefault(impact.skill_id, 0)
            old_by_skill[impact.skill_id] += impact.applied_delta

        skill_ids = {
            requirement.skill_id
            for assignment in assignments
            for requirement in requirements[assignment.id]
        }

        for skill_id in skill_ids:
            profile, _ = StudentSkill.objects.get_or_create(
                student=result.student,
                skill_id=skill_id,
                defaults={"score": 0, "note": "기본 과제 평가로 자동 생성"},
            )
            baseline = max(0, min(100, profile.score - old_by_skill.get(skill_id, 0)))
            running = baseline

            for assignment in assignments:
                requirement = next(
                    (item for item in requirements[assignment.id] if item.skill_id == skill_id),
                    None,
                )
                if not requirement:
                    continue

                raw_score = (
                    float(result.team_score)
                    if assignment.assignment_type == Assignment.AssignmentType.TEAM
                    else float(result.personal_score)
                )
                performance = max(0.0, min(100.0, raw_score * 20.0))
                delta = round(
                    (performance - running)
                    * (requirement.weight / 100)
                    * 0.30
                )
                next_score = max(0, min(100, running + delta))
                actual_delta = next_score - running

                AssignmentSkillImpact.objects.update_or_create(
                    assignment=assignment,
                    student=result.student,
                    skill_id=skill_id,
                    defaults={
                        "performance_score": performance,
                        "skill_weight": requirement.weight,
                        "previous_score": running,
                        "new_score": next_score,
                        "applied_delta": actual_delta,
                    },
                )
                running = next_score

            if profile.score != running:
                profile.score = running
                profile.save(update_fields=["score", "updated_at"])


def _badge_rank_map(evaluation_round, result_rows=None):
    """평가 80% + 연결된 역량 과제 평균 20%로 배지 전용 순위를 계산한다.

    연결된 완료 과제 평가가 없는 수강생은 기존 평가 최종점수 100%를 사용한다.
    StudentResult.rank 자체는 변경하지 않아 공식 평가 순위와 배지 산정을 분리한다.
    """
    if result_rows is None:
        result_rows = list(
            StudentResult.objects.filter(
                evaluation_round=evaluation_round,
                is_excluded=False,
            ).select_related("student")
        )

    hr_rows = (
        HRTaskEvaluation.objects.filter(
            task__evaluation_round=evaluation_round,
            task__status=HRTask.Status.COMPLETED,
        )
        .values("student_id")
        .annotate(avg_score=Avg("score"))
    )
    hr_avg_map = {
        row["student_id"]: float(row["avg_score"])
        for row in hr_rows
    }

    ranked = []
    for result in result_rows:
        evaluation_score = float(result.final_score)
        hr_score = hr_avg_map.get(result.student_id)
        if hr_score is None:
            badge_score = evaluation_score
        else:
            badge_score = evaluation_score * 0.80 + hr_score * 0.20
        ranked.append((result.student_id, badge_score, evaluation_score))

    ranked.sort(key=lambda row: (row[1], row[2]), reverse=True)

    rank_map = {}
    previous_key = None
    current_rank = 0
    for index, (student_id, badge_score, evaluation_score) in enumerate(ranked, start=1):
        key = (round(badge_score, 8), round(evaluation_score, 8))
        if key != previous_key:
            current_rank = index
            previous_key = key
        rank_map[student_id] = current_rank

    return rank_map


def _complete_team_evaluator_ids(evaluation_round):
    """팀 평가 의무를 전부 끝낸 평가자만 반환한다.

    예: 다른 팀 4개를 평가해야 하는 학생이 2개만 제출했다면,
    그 학생이 제출한 2개 팀 평가도 점수 집계에서는 전부 무효 처리한다.
    모든 대상 팀을 최종 제출한 순간부터 해당 학생의 제출분 전체가 반영된다.
    """
    active_teams = list(
        Team.objects.filter(
            evaluation_round=evaluation_round,
            is_active=True,
        ).values_list("id", flat=True)
    )
    if not active_teams:
        return set()

    memberships = {
        membership.student_id: membership.team_id
        for membership in TeamMembership.objects.filter(
            team__evaluation_round=evaluation_round,
            student__is_active=True,
            student__user__is_active=True,
        ).select_related("student__user")
    }
    if not memberships:
        return set()

    exempt_student_ids = set(
        RoundAttendance.objects.filter(
            evaluation_round=evaluation_round,
            student_id__in=memberships.keys(),
            status__in={
                RoundAttendance.Status.ABSENT,
                RoundAttendance.Status.EXCUSED,
            },
        ).values_list("student_id", flat=True)
    )

    submitted_map = {}
    submitted_pairs = TeamEvaluation.objects.filter(
        evaluation_round=evaluation_round,
        evaluator_id__in=memberships.keys(),
        target_team_id__in=active_teams,
        is_submitted=True,
    ).values_list("evaluator_id", "target_team_id")

    for evaluator_id, target_team_id in submitted_pairs:
        submitted_map.setdefault(evaluator_id, set()).add(target_team_id)

    complete_ids = set()
    active_team_set = set(active_teams)
    for evaluator_id, own_team_id in memberships.items():
        # 결석/공결자는 타팀 평가 의무 자체가 없으므로 집계 평가자로 사용하지 않는다.
        if evaluator_id in exempt_student_ids:
            continue

        required_targets = active_team_set - {own_team_id}
        if not required_targets:
            continue

        submitted_targets = submitted_map.get(evaluator_id, set()) & required_targets
        if submitted_targets >= required_targets:
            complete_ids.add(evaluator_id)

    return complete_ids


def _complete_personal_evaluator_ids(evaluation_round):
    """개인 평가 의무를 전부 끝낸 평가자만 반환한다.

    같은 팀에서 본인을 제외한 평가 대상 전원을 최종 제출해야
    그 평가자의 개인 평가 데이터 전체가 점수 계산에 포함된다.
    """
    memberships = list(
        TeamMembership.objects.filter(
            team__evaluation_round=evaluation_round,
            student__is_active=True,
            student__user__is_active=True,
        ).values_list("student_id", "team_id")
    )
    if not memberships:
        return set()

    team_members = {}
    student_team = {}
    for student_id, team_id in memberships:
        student_team[student_id] = team_id
        team_members.setdefault(team_id, set()).add(student_id)

    submitted_map = {}
    submitted_pairs = PersonalEvaluation.objects.filter(
        evaluation_round=evaluation_round,
        evaluator_id__in=student_team.keys(),
        is_submitted=True,
    ).values_list("evaluator_id", "target_student_id")

    for evaluator_id, target_student_id in submitted_pairs:
        submitted_map.setdefault(evaluator_id, set()).add(target_student_id)

    complete_ids = set()
    for evaluator_id, team_id in student_team.items():
        required_targets = team_members.get(team_id, set()) - {evaluator_id}
        if not required_targets:
            continue

        submitted_targets = submitted_map.get(evaluator_id, set()) & required_targets
        if submitted_targets >= required_targets:
            complete_ids.add(evaluator_id)

    return complete_ids


def _recalculate_round_results(evaluation_round):
    """팀 40% + 개인 60% 기준 결과를 다시 계산한다.

    핵심 규칙:
    - 평가자가 본인의 필수 평가 대상을 전부 최종 제출해야 그 평가자의 데이터 전체를 반영한다.
    - 일부만 제출한 평가자는 제출한 대상까지 포함해 해당 회차 점수 집계에서 전부 제외한다.
    - 모든 필수 평가를 완료한 순간 그 평가자의 기존 제출분 전체가 다시 반영된다.

    팀 점수: '팀 평가 전체 완료자'가 해당 팀에 준 점수의 평균
    개인 점수: '개인 평가 전체 완료자'가 해당 학생에게 준 점수의 평균
    최종 점수: 회차별 개인/팀 가중치 적용 + 관리자 보정점수
    """
    # 재계산 전에 이전 순위/제외 상태를 초기화해 팀 이동·비활성화 후에도 낡은 결과가 남지 않게 한다.
    TeamResult.objects.filter(evaluation_round=evaluation_round).update(is_excluded=True, rank=None)
    StudentResult.objects.filter(evaluation_round=evaluation_round).update(is_excluded=True, rank=None)

    complete_team_evaluator_ids = _complete_team_evaluator_ids(evaluation_round)
    complete_personal_evaluator_ids = _complete_personal_evaluator_ids(evaluation_round)

    teams = Team.objects.filter(evaluation_round=evaluation_round, is_active=True)
    team_score_map = {}

    for team in teams:
        team_score_qs = TeamEvaluationScore.objects.filter(
            evaluation__evaluation_round=evaluation_round,
            evaluation__target_team=team,
            evaluation__evaluator_id__in=complete_team_evaluator_ids,
            evaluation__is_submitted=True,
        )
        team_avg = team_score_qs.aggregate(avg=Avg("score"))["avg"] or 0
        valid_team_evaluations = TeamEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            target_team=team,
            evaluator_id__in=complete_team_evaluator_ids,
            is_submitted=True,
        ).count()
        team_excluded = valid_team_evaluations == 0
        team_score_map[team.id] = float(team_avg)
        TeamResult.objects.update_or_create(
            evaluation_round=evaluation_round,
            team=team,
            defaults={"score": team_avg, "is_excluded": team_excluded},
        )

    memberships = (
        TeamMembership.objects.filter(team__evaluation_round=evaluation_round)
        .select_related("student", "team")
    )
    student_team_map = {m.student_id: m.team for m in memberships}

    students = Student.objects.filter(
        id__in=student_team_map.keys(), is_active=True, user__is_active=True
    ).select_related("user")

    result_rows = []
    for student in students:
        personal_score_qs = PersonalEvaluationScore.objects.filter(
            evaluation__evaluation_round=evaluation_round,
            evaluation__target_student=student,
            evaluation__evaluator_id__in=complete_personal_evaluator_ids,
            evaluation__is_submitted=True,
        )
        personal_avg = personal_score_qs.aggregate(avg=Avg("score"))["avg"] or 0
        valid_personal_evaluations = PersonalEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            target_student=student,
            evaluator_id__in=complete_personal_evaluator_ids,
            is_submitted=True,
        ).count()
        team = student_team_map.get(student.id)
        team_avg = team_score_map.get(team.id, 0) if team else 0
        team_result = TeamResult.objects.filter(evaluation_round=evaluation_round, team=team).first() if team else None
        excluded = valid_personal_evaluations == 0 or not team_result or team_result.is_excluded
        personal_weight = float(evaluation_round.personal_weight) / 100
        team_weight = float(evaluation_round.team_weight) / 100
        base_score = float(personal_avg) * personal_weight + float(team_avg) * team_weight
        existing_result = StudentResult.objects.filter(evaluation_round=evaluation_round, student=student).first()
        adjustment_score = float(existing_result.adjustment_score) if existing_result else 0
        final_score = base_score + adjustment_score
        result, _ = StudentResult.objects.update_or_create(
            evaluation_round=evaluation_round,
            student=student,
            defaults={
                "team_score": team_avg,
                "personal_score": personal_avg,
                "base_score": base_score,
                "final_score": final_score,
                "is_excluded": excluded,
            },
        )
        if not excluded:
            result_rows.append(result)

    # 공동 점수는 같은 등수, 다음 등수는 건너뛰는 competition ranking.
    ordered = sorted(
        result_rows,
        key=lambda r: (float(r.final_score), float(r.personal_score)),
        reverse=True,
    )
    previous_key = None
    current_rank = 0
    for index, result in enumerate(ordered, start=1):
        key = (result.final_score, result.personal_score)
        if key != previous_key:
            current_rank = index
            previous_key = key
        if result.rank != current_rank:
            result.rank = current_rank
            result.save(update_fields=["rank", "updated_at"])

    # 종료된 기본 과제의 결과를 역량 프로필에 반영한다.
    _apply_assignment_skill_impacts(evaluation_round, ordered)

    # 배지 산정은 공식 최종점수와 분리한다.
    # 역량 과제가 회차에 연결되어 평가 완료된 경우:
    #   배지점수 = 기존 평가 최종점수 80% + 역량 과제 평균점수 20%
    # 연결된 과제 평가가 없는 수강생은 기존 평가 최종점수를 그대로 사용한다.
    current_badge_ranks = _badge_rank_map(evaluation_round, ordered)

    # MVP: 배지 전용 순위 1위. 동점은 공동 수상.
    mvp_student_ids = [
        student_id
        for student_id, rank in current_badge_ranks.items()
        if rank == 1
    ]
    StudentBadge.objects.filter(
        evaluation_round=evaluation_round,
        badge_type=StudentBadge.BadgeType.MVP,
    ).exclude(student_id__in=mvp_student_ids).delete()
    for student_id in mvp_student_ids:
        StudentBadge.objects.get_or_create(
            evaluation_round=evaluation_round,
            student_id=student_id,
            badge_type=StudentBadge.BadgeType.MVP,
        )

    previous_round = (
        EvaluationRound.objects.filter(
            start_at__lt=evaluation_round.start_at,
            status=EvaluationRound.Status.ENDED,
        )
        .order_by("-start_at")
        .first()
    )
    previous_badge_ranks = _badge_rank_map(previous_round) if previous_round else {}

    # 성장왕: 직전 회차 대비 배지 전용 순위가 가장 많이 상승한 학생.
    growth_student_ids = []
    improvements = []
    for student_id, current_rank in current_badge_ranks.items():
        previous_rank = previous_badge_ranks.get(student_id)
        if previous_rank:
            improvement = previous_rank - current_rank
            if improvement > 0:
                improvements.append((student_id, improvement))

    if improvements:
        best_improvement = max(improvement for _, improvement in improvements)
        growth_student_ids = [
            student_id
            for student_id, improvement in improvements
            if improvement == best_improvement
        ]

    StudentBadge.objects.filter(
        evaluation_round=evaluation_round,
        badge_type=StudentBadge.BadgeType.GROWTH,
    ).exclude(student_id__in=growth_student_ids).delete()
    for student_id in growth_student_ids:
        StudentBadge.objects.get_or_create(
            evaluation_round=evaluation_round,
            student_id=student_id,
            badge_type=StudentBadge.BadgeType.GROWTH,
        )

    # 연속 우수: 직전/현재 회차의 배지 전용 순위가 모두 Top 3.
    current_top3_ids = {
        student_id
        for student_id, rank in current_badge_ranks.items()
        if rank <= 3
    }
    previous_top3_ids = {
        student_id
        for student_id, rank in previous_badge_ranks.items()
        if rank <= 3
    }
    consistent_student_ids = sorted(current_top3_ids & previous_top3_ids)

    StudentBadge.objects.filter(
        evaluation_round=evaluation_round,
        badge_type=StudentBadge.BadgeType.CONSISTENT,
    ).exclude(student_id__in=consistent_student_ids).delete()
    for student_id in consistent_student_ids:
        StudentBadge.objects.get_or_create(
            evaluation_round=evaluation_round,
            student_id=student_id,
            badge_type=StudentBadge.BadgeType.CONSISTENT,
        )

    team_results = list(TeamResult.objects.filter(evaluation_round=evaluation_round, is_excluded=False))
    team_results.sort(key=lambda r: float(r.score), reverse=True)
    previous_score = None
    current_rank = 0
    for index, result in enumerate(team_results, start=1):
        if result.score != previous_score:
            current_rank = index
            previous_score = result.score
        if result.rank != current_rank:
            result.rank = current_rank
            result.save(update_fields=["rank", "updated_at"])

def _current_round():
    """관리자가 지정한 현재 회차를 우선 반환한다. 지정값이 없으면 기존 규칙으로 보정한다."""
    selected = EvaluationRound.objects.filter(is_current=True).order_by("-updated_at").first()
    if selected:
        return selected
    return (
        EvaluationRound.objects.filter(status=EvaluationRound.Status.IN_PROGRESS)
        .order_by("-start_at")
        .first()
        or EvaluationRound.objects.filter(status=EvaluationRound.Status.SCHEDULED)
        .order_by("start_at")
        .first()
        or EvaluationRound.objects.order_by("-start_at").first()
    )

def _round_teams(evaluation_round):
    if not evaluation_round:
        return Team.objects.none()
    return Team.objects.filter(evaluation_round=evaluation_round, is_active=True).order_by("name")

def _sync_student_team(student, team, evaluation_round):
    """현재 관리 회차에 대해서만 소속 팀을 변경한다. 과거 회차 기록은 보존한다."""
    if not evaluation_round:
        return

    memberships = TeamMembership.objects.filter(
        student=student,
        team__evaluation_round=evaluation_round,
    )

    if team is None:
        memberships.delete()
        return

    memberships.exclude(team=team).delete()
    TeamMembership.objects.get_or_create(team=team, student=student)

def _normalize_excel_header(value):
    return str(value or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")

def _excel_bool(value, default=True):
    if value is None or str(value).strip() == "":
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "활성", "사용", "사용중", "o", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "비활성", "미사용", "x", "off"}:
        return False
    raise ValueError("활성 상태는 활성/비활성, O/X, TRUE/FALSE 중 하나로 입력해주세요.")

def _invalidate_user_sessions(user_id):
    """비밀번호 초기화 후 해당 사용자의 기존 로그인 세션을 제거한다."""
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        try:
            data = session.get_decoded()
            if str(data.get("_auth_user_id")) == str(user_id):
                session.delete()
        except Exception:
            continue

def _calculated_round_status(evaluation_round, now=None):
    """회차 상태는 날짜가 아니라 관리자 액션으로 전환한다."""
    return evaluation_round.status

def _sync_round_statuses():
    """수동 회차 흐름을 사용하므로 상태를 날짜 기준으로 자동 변경하지 않는다."""
    return None

def _assignment_editable(assignment):
    round_obj = assignment.evaluation_round
    return (
        round_obj.status in {EvaluationRound.Status.SCHEDULED, EvaluationRound.Status.IN_PROGRESS}
        and not round_obj.evaluation_started
    )

def _cumulative_seed_scores_before(evaluation_round):
    """현재 회차 이전의 확정 결과를 회차별 seed_weight로 가중 평균한다.

    관리자가 각 종료 회차에 0~100 가중치를 줄 수 있다.
    예: 최근 100 / 직전 80 / 2회 전 60.
    가중치가 0인 회차는 다음 팀 편성 Seed에서 제외된다.
    """
    previous_results = (
        StudentResult.objects.filter(
            evaluation_round__start_at__lt=evaluation_round.start_at,
            evaluation_round__status=EvaluationRound.Status.ENDED,
            is_excluded=False,
        )
        .exclude(final_score__isnull=True)
        .select_related("evaluation_round")
        .order_by("evaluation_round__start_at", "student_id")
    )

    weighted_totals = {}
    weight_totals = {}

    for result in previous_results:
        round_obj = result.evaluation_round
        history_weight = int(round_obj.seed_weight or 0)
        if history_weight <= 0:
            continue

        team_weight = int(round_obj.seed_team_weight or 0)
        personal_weight = int(round_obj.seed_personal_weight or 0)
        score_weight_total = team_weight + personal_weight
        if score_weight_total <= 0:
            continue

        # 실제 성적(final_score)은 RFP 기본 산식을 유지하고,
        # 팀 편성용 Seed만 별도 팀/개인 비율로 재계산한다.
        seed_base_score = (
            (result.team_score * Decimal(team_weight))
            + (result.personal_score * Decimal(personal_weight))
        ) / Decimal(score_weight_total)

        weighted_totals[result.student_id] = (
            weighted_totals.get(result.student_id, Decimal("0"))
            + (seed_base_score * Decimal(history_weight))
        )
        weight_totals[result.student_id] = (
            weight_totals.get(result.student_id, 0) + history_weight
        )

    return {
        student_id: weighted_totals[student_id] / Decimal(weight_totals[student_id])
        for student_id in weighted_totals
        if weight_totals.get(student_id)
    }

def _previous_round_for(evaluation_round):
    if not evaluation_round:
        return None
    return (
        EvaluationRound.objects
        .filter(
            start_at__lt=evaluation_round.start_at,
            student_results__isnull=False,
        )
        .distinct()
        .order_by("-start_at", "-id")
        .first()
    )

def _snake_seed_assignment(students, team_count, seed_scores):
    """성적순 Z(스네이크) 편성.

    예: 4팀이면 1~4위 -> 1,2,3,4팀 / 5~8위 -> 4,3,2,1팀.
    따라서 각 시드 그룹의 상·하위 학생이 팀마다 번갈아 배치된다.
    """
    ordered = sorted(
        students,
        key=lambda student: (float(seed_scores.get(student.id, 0)), -student.id),
        reverse=True,
    )
    buckets = [[] for _ in range(team_count)]
    for index, student in enumerate(ordered):
        row = index // team_count
        position = index % team_count
        team_index = position if row % 2 == 0 else team_count - 1 - position
        buckets[team_index].append(student)
    return buckets

def _pot_seed_assignment(students, team_count, seed_scores, previous_team_map=None):
    """누적 Seed 기반 FIFA 포트 추첨.

    A/B/C/D 누적 기준은 20% / 30% / 80% / 100%.
    소수 인원에서도 A 포트가 사라지지 않도록 누적 인원 경계는 ceil로 계산한다.
    Seed가 전혀 없는 학생은 U(미분류)로 두고 마지막에 균등 랜덤 배치한다.
    """
    previous_team_map = previous_team_map or {}
    seeded = [student for student in students if student.id in seed_scores]
    unseeded = [student for student in students if student.id not in seed_scores]
    ordered = sorted(
        seeded,
        key=lambda student: (float(seed_scores.get(student.id, 0)), -student.id),
        reverse=True,
    )
    total = len(ordered)

    grade_map = {student.id: "U" for student in unseeded}
    pots = {"A": [], "B": [], "C": [], "D": []}
    a_cut = math.ceil(total * 0.20) if total else 0
    b_cut = math.ceil(total * 0.30) if total else 0
    c_cut = math.ceil(total * 0.80) if total else 0

    for rank, student in enumerate(ordered, start=1):
        if rank <= a_cut:
            grade = "A"
        elif rank <= b_cut:
            grade = "B"
        elif rank <= c_cut:
            grade = "C"
        else:
            grade = "D"
        grade_map[student.id] = grade
        pots[grade].append(student)

    for grade in pots:
        random.shuffle(pots[grade])
    random.shuffle(unseeded)

    total_students = len(students)
    base_size = total_students // team_count
    extra = total_students % team_count
    capacities = [base_size + (1 if idx < extra else 0) for idx in range(team_count)]
    buckets = [[] for _ in range(team_count)]
    bucket_grade_counts = [{grade: 0 for grade in ("A", "B", "C", "D", "U")} for _ in range(team_count)]
    bucket_previous_teams = [set() for _ in range(team_count)]

    def place(student, grade):
        prev_team = previous_team_map.get(student.id)
        candidates = [idx for idx in range(team_count) if len(buckets[idx]) < capacities[idx]]
        if not candidates:
            candidates = list(range(team_count))
        candidates.sort(
            key=lambda idx: (
                bucket_grade_counts[idx][grade],
                1 if prev_team and prev_team in bucket_previous_teams[idx] else 0,
                len(buckets[idx]),
                random.random(),
            )
        )
        chosen = candidates[0]
        buckets[chosen].append(student)
        bucket_grade_counts[chosen][grade] += 1
        if prev_team:
            bucket_previous_teams[chosen].add(prev_team)

    for grade in ("A", "B", "C", "D"):
        for student in pots[grade]:
            place(student, grade)
    for student in unseeded:
        place(student, "U")

    return buckets, grade_map, {
        "A": len(pots["A"]), "B": len(pots["B"]), "C": len(pots["C"]), "D": len(pots["D"]),
        "U": len(unseeded),
    }


def _balanced_random_assignment(students, team_count, previous_team_map=None):
    """랜덤 균등 편성. 가능하면 직전 회차 같은 조합을 피한다."""
    previous_team_map = previous_team_map or {}
    students = list(students)
    random.shuffle(students)
    buckets = [[] for _ in range(team_count)]
    previous_sets = [set() for _ in range(team_count)]
    for student in students:
        candidate_order = sorted(range(team_count), key=lambda i: (len(buckets[i]), random.random()))
        chosen = None
        prev_team = previous_team_map.get(student.id)
        for idx in candidate_order:
            if prev_team and prev_team in previous_sets[idx]:
                continue
            chosen = idx
            break
        if chosen is None:
            chosen = candidate_order[0]
        buckets[chosen].append(student)
        if prev_team:
            previous_sets[chosen].add(prev_team)
    return buckets

def _selected_round(request, rounds=None):
    rounds = rounds if rounds is not None else EvaluationRound.objects.all().order_by("-start_at")
    round_id = request.GET.get("round") or request.POST.get("round_id")
    if round_id:
        return rounds.filter(pk=round_id).first()
    return rounds.first()

def _active_announcements(student=None):
    now = timezone.now()
    qs = Announcement.objects.filter(
        is_published=True,
        target_all=True,
        publish_at__lte=now,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    return qs.order_by("-publish_at", "-id")

def _parse_optional_datetime(value):
    value = (value or "").strip()
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


__all__ = [name for name in globals() if not name.startswith('__')]
