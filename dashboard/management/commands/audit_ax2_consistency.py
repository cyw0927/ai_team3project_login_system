from collections import Counter
from pathlib import Path
import re

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Count, Q

from dashboard.models import (
    Assignment,
    EvaluationRound,
    EvaluationTemplate,
    PersonalEvaluation,
    RoundAttendance,
    Student,
    StudentResult,
    Team,
    TeamAssignmentSubmission,
    TeamEvaluation,
    TeamMembership,
    TeamResult,
)
from dashboard.services.admin_dashboard_service import build_admin_dashboard_context


RAW_TABLE = "dashboard_officialevaluationresponse"


class Command(BaseCommand):
    help = "현재 AX2 회차의 DB/화면 핵심 수치가 서로 모순되지 않는지 전수 점검합니다."

    def handle(self, *args, **options):
        round_obj = (
            EvaluationRound.objects.filter(is_current=True).order_by("-start_at", "-id").first()
            or EvaluationRound.objects.order_by("-start_at", "-id").first()
        )
        if not round_obj:
            self.stdout.write(self.style.ERROR("평가 회차가 없습니다."))
            return

        errors = []
        warnings = []
        ok = []

        all_students = Student.objects.select_related("user")
        total_students = all_students.count()
        active_students = all_students.filter(is_active=True, user__is_active=True).count()
        inactive_students = all_students.filter(
            Q(is_active=False) | Q(user__is_active=False)
        ).distinct().count()

        teams = list(
            Team.objects.filter(evaluation_round=round_obj, is_active=True).order_by("name")
        )
        memberships = list(
            TeamMembership.objects.filter(
                team__evaluation_round=round_obj,
                team__is_active=True,
            ).select_related("team", "student__user")
        )
        membership_ids = [m.student_id for m in memberships]
        distinct_member_ids = set(membership_ids)
        distinct_members = len(distinct_member_ids)
        team_sizes = Counter(m.team.name for m in memberships)

        self.stdout.write(
            self.style.MIGRATE_HEADING(f"AX2 데이터 일관성 전수점검: {round_obj.name}")
        )
        self.stdout.write(
            f"수강생 DB: 전체 {total_students} / 활성 {active_students} / 비활성 {inactive_students}"
        )
        self.stdout.write(
            f"현재 회차: 활성 팀 {len(teams)} / 팀 배정 학생 {distinct_members}"
        )
        self.stdout.write(
            "팀별 인원: "
            + ", ".join(
                f"{name} {count}명" for name, count in sorted(team_sizes.items())
            )
        )

        # 1) 학생/팀 배정 일관성
        duplicate_memberships = [
            (student_id, count)
            for student_id, count in Counter(membership_ids).items()
            if count > 1
        ]
        if duplicate_memberships:
            errors.append(
                "한 회차에 중복 팀 배정 학생이 있습니다: "
                + ", ".join(f"student_id={sid}×{count}" for sid, count in duplicate_memberships)
            )
        else:
            ok.append("회차 내 학생별 팀 배정은 정확히 1개 이하입니다.")

        active_ids = set(
            all_students.filter(is_active=True, user__is_active=True).values_list("id", flat=True)
        )
        unassigned_active = sorted(active_ids - distinct_member_ids)
        inactive_but_assigned = sorted(distinct_member_ids - active_ids)
        if unassigned_active:
            errors.append(
                f"활성 수강생 중 현재 회차 미배정 {len(unassigned_active)}명: {unassigned_active[:12]}"
            )
        else:
            ok.append("활성 수강생 전원이 현재 회차에 배정되어 있습니다.")
        if inactive_but_assigned:
            warnings.append(
                f"비활성인데 현재 회차 팀에 남은 학생 {len(inactive_but_assigned)}명: {inactive_but_assigned[:12]}"
            )

        if active_students != distinct_members:
            errors.append(
                f"활성 수강생 {active_students}명 != 현재 회차 팀 배정 학생 {distinct_members}명"
            )
        else:
            ok.append("활성 수강생 수와 현재 회차 배정 학생 수가 같습니다.")

        # 2) 제출 필요량/실제 제출량
        present_ids = set(
            RoundAttendance.objects.filter(
                evaluation_round=round_obj,
                status=RoundAttendance.Status.PRESENT,
                student_id__in=membership_ids,
            ).values_list("student_id", flat=True)
        )
        attendance_count = RoundAttendance.objects.filter(
            evaluation_round=round_obj,
            student_id__in=membership_ids,
        ).count()
        if attendance_count != distinct_members:
            warnings.append(
                f"출결 레코드 {attendance_count}건 != 팀 배정 학생 {distinct_members}명"
            )
        else:
            ok.append("현재 회차 출결 레코드와 팀 배정 학생 수가 같습니다.")

        team_count = len(teams)
        expected_team = sum(
            max(team_count - 1, 0)
            for sid in distinct_member_ids
            if sid in present_ids
        )
        expected_personal = sum(size * max(size - 1, 0) for size in team_sizes.values())

        submitted_team_pairs = set(
            TeamEvaluation.objects.filter(
                evaluation_round=round_obj,
                evaluator__is_active=True,
                evaluator__user__is_active=True,
                is_submitted=True,
            ).values_list("evaluator_id", "target_team_id")
        )
        submitted_personal_pairs = set(
            PersonalEvaluation.objects.filter(
                evaluation_round=round_obj,
                evaluator__is_active=True,
                evaluator__user__is_active=True,
                is_submitted=True,
            ).values_list("evaluator_id", "target_student_id")
        )
        submitted_team = len(submitted_team_pairs)
        submitted_personal = len(submitted_personal_pairs)

        team_missing = max(expected_team - submitted_team, 0)
        personal_missing = max(expected_personal - submitted_personal, 0)
        required_total = expected_team + expected_personal
        submitted_total = min(submitted_team, expected_team) + min(
            submitted_personal, expected_personal
        )
        completion = round((submitted_total / required_total) * 100) if required_total else 0

        self.stdout.write("")
        self.stdout.write(
            f"팀평가: 제출 {submitted_team}/{expected_team} / 미제출 {team_missing}"
        )
        self.stdout.write(
            f"개인평가: 제출 {submitted_personal}/{expected_personal} / 미제출 {personal_missing}"
        )
        self.stdout.write(
            f"통합 진행률: {submitted_total}/{required_total} = {completion}% / 총 미제출 {team_missing + personal_missing}"
        )

        # 3) 관리자 홈 서비스가 같은 기준을 쓰는지
        dashboard_context = build_admin_dashboard_context(round_obj)
        dashboard_stats = dashboard_context.get("stats", {})
        dashboard_expected = {
            "student_count": active_students,
            "active_team_count": team_count,
            "team_submission_count": submitted_team,
            "team_required": expected_team,
            "personal_submission_count": submitted_personal,
            "personal_required": expected_personal,
            "missing_submission_count": team_missing + personal_missing,
            "overall_percent": completion,
        }
        for key, expected in dashboard_expected.items():
            actual = dashboard_stats.get(key)
            if actual != expected:
                errors.append(f"관리자 홈 {key}: 표시 기준 {actual} != canonical {expected}")
            else:
                ok.append(f"관리자 홈 {key}={expected} 일치")

        # 4) 규칙 위반 canonical 행
        self_target_team = 0
        for evaluation in TeamEvaluation.objects.filter(
            evaluation_round=round_obj
        ).select_related("target_team"):
            if evaluation.target_team.memberships.filter(
                student_id=evaluation.evaluator_id
            ).exists():
                self_target_team += 1
        if self_target_team:
            errors.append(
                f"자기 팀을 평가한 canonical 팀평가가 {self_target_team}건 남아 있습니다."
            )
        else:
            ok.append("자기 팀 평가 canonical 행은 없습니다.")

        self_target_personal = PersonalEvaluation.objects.filter(
            evaluation_round=round_obj,
        ).filter(evaluator_id__in=distinct_member_ids).count()
        invalid_personal = 0
        membership_team_by_student = {m.student_id: m.team_id for m in memberships}
        for evaluation in PersonalEvaluation.objects.filter(
            evaluation_round=round_obj
        ).only("evaluator_id", "target_student_id"):
            if evaluation.evaluator_id == evaluation.target_student_id:
                invalid_personal += 1
                continue
            if membership_team_by_student.get(evaluation.evaluator_id) != membership_team_by_student.get(
                evaluation.target_student_id
            ):
                invalid_personal += 1
        if invalid_personal:
            errors.append(f"개인평가 규칙 위반 canonical 행이 {invalid_personal}건 있습니다.")
        else:
            ok.append("개인평가 canonical 행은 같은 팀·자기 제외 규칙을 만족합니다.")

        # 5) 결과/템플릿/과제 건수
        student_result_count = StudentResult.objects.filter(
            evaluation_round=round_obj
        ).count()
        team_result_count = TeamResult.objects.filter(evaluation_round=round_obj).count()
        if student_result_count != distinct_members:
            errors.append(
                f"학생 결과 {student_result_count}건 != 팀 배정 학생 {distinct_members}명"
            )
        else:
            ok.append("학생 결과 건수와 팀 배정 학생 수가 같습니다.")
        if team_result_count != team_count:
            errors.append(f"팀 결과 {team_result_count}건 != 활성 팀 {team_count}개")
        else:
            ok.append("팀 결과 건수와 활성 팀 수가 같습니다.")

        team_templates = EvaluationTemplate.objects.filter(
            evaluation_round=round_obj,
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
            is_active=True,
        )
        personal_templates = EvaluationTemplate.objects.filter(
            evaluation_round=round_obj,
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
            is_active=True,
        )
        team_criteria = sum(template.criteria.count() for template in team_templates)
        personal_criteria = sum(
            template.criteria.count() for template in personal_templates
        )
        if team_templates.count() != 1 or team_criteria != 5:
            errors.append(
                f"팀 템플릿 상태 이상: 템플릿 {team_templates.count()}개 / 문항 {team_criteria}개"
            )
        else:
            ok.append("팀 평가 템플릿 1개 / 5문항입니다.")
        if personal_templates.count() != 1 or personal_criteria != 5:
            errors.append(
                f"개인 템플릿 상태 이상: 템플릿 {personal_templates.count()}개 / 문항 {personal_criteria}개"
            )
        else:
            ok.append("개인 평가 템플릿 1개 / 5문항입니다.")

        bad_scale_count = 0
        for template in list(team_templates) + list(personal_templates):
            for criterion in template.criteria.all():
                if criterion.max_score != 5 or not criterion.is_required:
                    bad_scale_count += 1
        if bad_scale_count:
            errors.append(f"5점 필수 문항 규칙 위반 문항 {bad_scale_count}개")
        else:
            ok.append("현재 회차 평가 문항은 모두 필수·5점 척도입니다.")

        assignment = Assignment.objects.filter(
            evaluation_round=round_obj,
            assignment_type=Assignment.AssignmentType.TEAM,
        ).first()
        if assignment:
            submission_count = TeamAssignmentSubmission.objects.filter(
                assignment=assignment
            ).count()
            if submission_count != team_count:
                errors.append(
                    f"조별과제 제출 {submission_count}/{team_count}: 회차 준비도와 불일치"
                )
            else:
                ok.append(f"조별과제 제출 {submission_count}/{team_count}입니다.")
        else:
            warnings.append("현재 회차 조별과제가 없습니다.")

        # 6) 원본 archive 보존/legacy 완료 오인 방지
        if RAW_TABLE in connection.introspection.table_names():
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT response_type, COUNT(*) FROM {RAW_TABLE} WHERE evaluation_round_id=%s GROUP BY response_type",
                    [round_obj.id],
                )
                raw_counts = dict(cursor.fetchall())
            if raw_counts:
                rendered = ", ".join(
                    f"{key}={value}" for key, value in sorted(raw_counts.items())
                )
                self.stdout.write(f"원본 보관 행: {rendered}")
                if (
                    raw_counts.get("personal_source") == 101
                    and raw_counts.get("team_source") == 66
                ):
                    ok.append("AX2 원본 101+66행이 source archive로 보존되어 있습니다.")
                else:
                    errors.append(
                        "AX2 source archive 건수가 기대값(personal_source=101, team_source=66)과 다릅니다."
                    )
                if raw_counts.get("personal") or raw_counts.get("team"):
                    errors.append(
                        "legacy 완료-import 타입(team/personal)이 현재 회차에 남아 있어 100%로 오인될 수 있습니다."
                    )
        else:
            errors.append("공식 원본 archive 테이블이 없습니다.")

        # 7) 학생 표시명/재구축 상태
        duplicate_names = list(
            Student.objects.values("user__first_name")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )
        if duplicate_names:
            errors.append(
                "표시명이 완전히 같은 학생이 남아 있습니다: "
                + ", ".join(
                    f"{row['user__first_name']}×{row['count']}" for row in duplicate_names
                )
            )
        else:
            ok.append("현재 학생 표시명은 서로 구분됩니다.")

        old_projection_count = Student.objects.filter(
            affiliation="AX2 공식 익명화 데이터"
        ).count()
        rebuilt_count = Student.objects.filter(
            affiliation="AX2 공식 재구축 데이터"
        ).count()
        if old_projection_count:
            errors.append(
                f"구형 24명 projection 학생이 {old_projection_count}명 남아 있습니다."
            )
        if rebuilt_count != total_students:
            warnings.append(
                f"재구축 데이터 소속 학생 {rebuilt_count}명 / 전체 학생 {total_students}명"
            )
        else:
            ok.append("전체 학생이 corrected AX2 재구축 데이터로 통일되어 있습니다.")

        # 8) 코드/템플릿의 24명 하드코딩 탐지
        project_root = Path(__file__).resolve().parents[3]
        suspect_files = []
        patterns = [
            re.compile(r"24\s*명"),
            re.compile(r"\b24\s*(students?|people|members?)\b", re.I),
        ]
        scan_roots = [project_root / "dashboard", project_root / "static"]
        allowed = {
            "dashboard/management/commands/audit_ax2_consistency.py",
        }
        for scan_root in scan_roots:
            if not scan_root.exists():
                continue
            for path in scan_root.rglob("*"):
                if path.suffix not in {".py", ".html", ".js", ".css"}:
                    continue
                relative = path.relative_to(project_root).as_posix()
                if relative in allowed:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                if any(pattern.search(text) for pattern in patterns):
                    suspect_files.append(relative)
        if suspect_files:
            warnings.append(
                "24명 하드코딩 의심 파일: " + ", ".join(sorted(set(suspect_files)))
            )
        else:
            ok.append("dashboard/static 코드에 24명 하드코딩 문자열이 없습니다.")

        self.stdout.write("")
        for message in ok:
            self.stdout.write(self.style.SUCCESS(f"[OK] {message}"))
        for message in warnings:
            self.stdout.write(self.style.WARNING(f"[WARN] {message}"))
        for message in errors:
            self.stdout.write(self.style.ERROR(f"[ERROR] {message}"))

        self.stdout.write("")
        if errors:
            self.stdout.write(
                self.style.ERROR(
                    f"점검 실패: 오류 {len(errors)}건 / 경고 {len(warnings)}건"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"점검 완료: 오류 0건 / 경고 {len(warnings)}건"
                )
            )
