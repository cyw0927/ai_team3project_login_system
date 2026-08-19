from collections import Counter

from django.core.management.base import BaseCommand

from dashboard.models import (
    EvaluationRound, HRTask, Student, StudentResult, Team, TeamMembership,
)


class Command(BaseCommand):
    help = "배포 전 데이터 무결성·대량 데이터·팀편성·결과 상태를 읽기 전용으로 점검합니다."

    def handle(self, *args, **options):
        warnings = []
        ok = []

        student_count = Student.objects.filter(is_active=True, user__is_active=True).count()
        ok.append(f"활성 수강생 {student_count}명")
        if student_count >= 100:
            ok.append("대량 수강생 QA 기준(100명 이상) 충족")
        else:
            warnings.append("대량 데이터 QA를 위해 활성 수강생 100명 이상을 권장합니다.")

        current_round = EvaluationRound.objects.filter(is_current=True).first()
        if current_round:
            memberships = list(
                TeamMembership.objects.filter(
                    team__evaluation_round=current_round,
                    team__is_active=True,
                ).values_list("student_id", "team_id")
            )
            duplicate_students = [
                student_id for student_id, count in Counter(s for s, _ in memberships).items()
                if count > 1
            ]
            if duplicate_students:
                warnings.append(f"현재 회차 중복 팀배정 학생 {len(duplicate_students)}명")
            else:
                ok.append("현재 회차 중복 팀배정 없음")

            active_teams = Team.objects.filter(evaluation_round=current_round, is_active=True).count()
            ok.append(f"현재 회차 활성 팀 {active_teams}개")
            unassigned = Student.objects.filter(is_active=True, user__is_active=True).exclude(
                id__in=[student_id for student_id, _ in memberships]
            ).count()
            if unassigned:
                warnings.append(f"현재 회차 미배정 수강생 {unassigned}명")
            else:
                ok.append("현재 회차 전원 팀배정 완료")
        else:
            warnings.append("현재 회차가 지정되지 않았습니다.")

        bad_results = StudentResult.objects.filter(is_excluded=False, final_score__lt=0).count()
        if bad_results:
            warnings.append(f"음수 최종점수 {bad_results}건")
        else:
            ok.append("음수 최종점수 없음")

        overdue_tasks = sum(1 for task in HRTask.objects.exclude(status=HRTask.Status.COMPLETED) if task.is_overdue)
        ok.append(f"미완료 역량과제 중 지연 {overdue_tasks}건")

        self.stdout.write(self.style.SUCCESS("=== PASS/INFO ==="))
        for item in ok:
            self.stdout.write(f"- {item}")

        if warnings:
            self.stdout.write(self.style.WARNING("=== 확인 필요 ==="))
            for item in warnings:
                self.stdout.write(f"- {item}")
        else:
            self.stdout.write(self.style.SUCCESS("확인 필요 항목이 없습니다."))
