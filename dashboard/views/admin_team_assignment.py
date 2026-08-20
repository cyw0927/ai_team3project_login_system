"""Admin team-assignment views."""

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from .common import _base_context, _current_round, _redirect_back, admin_required
from ..models import EvaluationRound, Student, Team, TeamMembership


@admin_required
def admin_team_assignment(request):
    rounds = EvaluationRound.objects.all().order_by("-start_at")
    selected_round_id = request.GET.get("round") or request.POST.get("round_id")
    selected_round = rounds.filter(pk=selected_round_id).first() if selected_round_id else _current_round()

    teams = list(Team.objects.filter(evaluation_round=selected_round, is_active=True).order_by("name")) if selected_round else []
    memberships = (
        TeamMembership.objects.filter(team__in=teams)
        .select_related("student__user", "team")
        if teams else TeamMembership.objects.none()
    )
    member_map = {team.id: [] for team in teams}
    assigned_ids = set()
    for membership in memberships:
        member_map.setdefault(membership.team_id, []).append(membership)
        assigned_ids.add(membership.student_id)
    for team in teams:
        team.membership_rows = member_map.get(team.id, [])
        team.members = [membership.student for membership in team.membership_rows]

    unassigned_students = list(
        Student.objects.filter(is_active=True, user__is_active=True)
        .exclude(id__in=assigned_ids)
        .select_related("user")
        .order_by("user__first_name", "user__username")
    )

    preview_teams = request.session.get("team_assignment_preview", [])
    if preview_teams and str(request.session.get("team_assignment_round_id")) != str(getattr(selected_round, "id", "")):
        preview_teams = []

    pot_quality = None
    pot_quality_warnings = []
    if preview_teams and preview_teams[0].get("assignment_rule") == "pot":
        unseeded_count = sum(team.get("pot_counts", {}).get("U", 0) for team in preview_teams)
        if unseeded_count:
            pot_quality_warnings.append(f"Seed 미분류 {unseeded_count}명은 U로 균등 랜덤 배치")
        for grade in ("A", "B", "C", "D"):
            counts = [team.get("pot_counts", {}).get(grade, 0) for team in preview_teams]
            spread = max(counts) - min(counts) if counts else 0
            if spread > 1:
                pot_quality_warnings.append(f"{grade} POT 팀간 차이 {spread}명")
        if pot_quality_warnings:
            pot_quality = {
                "status": "warning",
                "label": "포트 분산 확인 필요",
                "message": "일부 포트가 특정 팀에 상대적으로 몰렸습니다. 다시 추첨하면 다른 조합을 확인할 수 있습니다.",
            }
        else:
            pot_quality = {
                "status": "good",
                "label": "포트 균형 양호",
                "message": "A/B/C/D 포트가 팀별로 가능한 범위 안에서 고르게 분산되었습니다.",
            }

    total_students = Student.objects.filter(is_active=True, user__is_active=True).count()
    assigned_count = len(assigned_ids)
    unassigned_count = len(unassigned_students)
    team_count = len(teams)
    average_team_size = round(assigned_count / team_count, 1) if team_count else 0
    largest_team_size = max((len(team.members) for team in teams), default=0)
    smallest_team_size = min((len(team.members) for team in teams), default=0) if teams else 0

    auto_settings = request.session.get("team_assignment_auto_settings", {})
    if str(auto_settings.get("round_id", "")) != str(getattr(selected_round, "id", "")):
        auto_settings = {}

    active_tab = request.GET.get("tab", "").strip().lower()
    if active_tab not in {"manual", "auto"}:
        active_tab = "auto" if preview_teams else "manual"

    return render(
        request,
        "admin_ui/team_assignment.html",
        _base_context(
            rounds=rounds,
            selected_round=selected_round,
            unassigned_students=unassigned_students,
            teams=teams,
            preview_teams=preview_teams,
            pot_quality=pot_quality,
            pot_quality_warnings=pot_quality_warnings,
            form_data={
                "team_count": auto_settings.get("team_count", len(teams) or ""),
                "assignment_rule": auto_settings.get("assignment_rule", "seed"),
                "avoid_previous": auto_settings.get("avoid_previous", "1"),
            },
            total_students=total_students,
            assigned_count=assigned_count,
            unassigned_count=unassigned_count,
            team_count=team_count,
            average_team_size=average_team_size,
            largest_team_size=largest_team_size,
            smallest_team_size=smallest_team_size,
            active_tab=active_tab,
        ),
    )


@admin_required
@require_POST
@transaction.atomic
def admin_manual_assign(request):
    round_id = request.POST.get("round_id")
    team_id = request.POST.get("team_id")
    student_ids = request.POST.getlist("student_ids")
    evaluation_round = get_object_or_404(EvaluationRound, pk=round_id)
    team = get_object_or_404(Team, pk=team_id, evaluation_round=evaluation_round)
    if not student_ids:
        messages.error(request, "배정할 수강생을 선택하세요.")
        return _redirect_back(request, f"/management/team-assignment/?round={round_id}")
    students = Student.objects.filter(pk__in=student_ids, is_active=True, user__is_active=True)
    for student in students:
        TeamMembership.objects.filter(student=student, team__evaluation_round=evaluation_round).delete()
        TeamMembership.objects.create(team=team, student=student)
    messages.success(request, f"{students.count()}명을 {team.name}에 배정했습니다.")
    return _redirect_back(request, f"/management/team-assignment/?round={round_id}")


@admin_required
@require_POST
@transaction.atomic
def admin_manual_unassign(request):
    round_id = request.POST.get("round_id")
    membership_ids = request.POST.getlist("membership_ids")
    if not membership_ids:
        messages.error(request, "배정을 해제할 팀원을 선택하세요.")
        return _redirect_back(request, f"/management/team-assignment/?round={round_id}")
    TeamMembership.objects.filter(
        pk__in=membership_ids,
        team__evaluation_round_id=round_id,
    ).delete()
    messages.success(request, "선택한 팀원의 배정을 해제했습니다.")
    return _redirect_back(request, f"/management/team-assignment/?round={round_id}")


@admin_required
@require_POST
@transaction.atomic
def admin_team_dissolve_all(request):
    round_id = request.POST.get("round_id", "").strip()
    evaluation_round = get_object_or_404(EvaluationRound, pk=round_id)
    memberships = TeamMembership.objects.filter(team__evaluation_round=evaluation_round)
    member_count = memberships.count()
    team_count = Team.objects.filter(evaluation_round=evaluation_round, is_active=True).count()
    if member_count == 0:
        messages.info(request, "현재 해체할 팀 배정이 없습니다.")
        return _redirect_back(request, f"/management/team-assignment/?round={evaluation_round.id}&tab=manual")
    memberships.delete()
    if str(request.session.get("team_assignment_round_id", "")) == str(evaluation_round.id):
        request.session.pop("team_assignment_preview", None)
        request.session.pop("team_assignment_round_id", None)
        request.session.modified = True
    messages.success(request, f"{team_count}개 팀의 {member_count}명 배정을 모두 해체했습니다. 팀 이름은 재편성을 위해 유지됩니다.")
    return _redirect_back(request, f"/management/team-assignment/?round={evaluation_round.id}&tab=manual")


@admin_required
@require_POST
def admin_team_member_role_update(request, membership_id):
    membership = get_object_or_404(
        TeamMembership.objects.select_related("team__evaluation_round", "student__user"),
        pk=membership_id,
    )
    role = request.POST.get("role", "").strip()
    if len(role) > 100:
        messages.error(request, "담당 역할은 100자 이하로 입력해 주세요.")
        return _redirect_back(request, f"/management/team-assignment/?round={membership.team.evaluation_round_id}&tab=manual")
    membership.role = role
    membership.save(update_fields=["role", "updated_at"])
    messages.success(request, f"{membership.student.name}님의 담당 역할을 저장했습니다.")
    return _redirect_back(request, f"/management/team-assignment/?round={membership.team.evaluation_round_id}&tab=manual#manual")


@admin_required
@require_POST
@transaction.atomic
def admin_auto_confirm(request):
    round_id = request.POST.get("round_id")
    evaluation_round = get_object_or_404(EvaluationRound, pk=round_id)
    preview = request.session.get("team_assignment_preview", [])
    preview_round_id = request.session.get("team_assignment_round_id")
    if not preview or str(preview_round_id) != str(evaluation_round.id):
        messages.error(request, "확정할 자동 편성 미리보기가 없습니다.")
        return _redirect_back(request, f"/management/team-assignment/?round={round_id}&tab=auto")

    TeamMembership.objects.filter(team__evaluation_round=evaluation_round).delete()
    existing = {team.name: team for team in Team.objects.filter(evaluation_round=evaluation_round)}
    used_team_ids = []
    for team_data in preview:
        team = existing.get(team_data["name"])
        if team is None:
            team = Team.objects.create(evaluation_round=evaluation_round, name=team_data["name"], is_active=True)
        elif not team.is_active:
            team.is_active = True
            team.save(update_fields=["is_active", "updated_at"])
        used_team_ids.append(team.id)
        students = Student.objects.filter(pk__in=team_data["student_ids"], is_active=True, user__is_active=True)
        TeamMembership.objects.bulk_create([TeamMembership(team=team, student=student) for student in students])

    Team.objects.filter(evaluation_round=evaluation_round).exclude(pk__in=used_team_ids).update(is_active=False)
    request.session.pop("team_assignment_preview", None)
    request.session.pop("team_assignment_round_id", None)
    request.session.modified = True
    messages.success(request, "자동 팀 편성을 확정하여 DB에 반영했습니다.")
    return _redirect_back(request, f"/management/team-assignment/?round={round_id}&tab=auto")
