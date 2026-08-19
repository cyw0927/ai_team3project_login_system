from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from dashboard.models import (
    Assignment,
    EvaluationCriterion,
    EvaluationRound,
    EvaluationTemplate,
    PersonalEvaluation,
    PersonalEvaluationScore,
    ResultPublishSetting,
    Student,
    StudentResult,
    Team,
    TeamEvaluation,
    TeamEvaluationScore,
    TeamMembership,
    TeamResult,
)


class Command(BaseCommand):
    help = "발표 시연용 관리자/학생/회차/팀/평가/결과 데이터를 생성합니다."

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()

        # 관리자
        admin, _ = User.objects.get_or_create(username="demo_admin")
        admin.first_name = "발표관리자"
        admin.email = "demo_admin@example.com"
        admin.is_staff = True
        admin.is_superuser = True
        admin.is_active = True
        admin.set_password("Demo1234!")
        admin.save()

        # 재실행 가능하게 데모 학생 정리
        usernames = [f"demo{i:02d}" for i in range(1, 13)]
        User.objects.filter(username__in=usernames).delete()

        students = []
        for i in range(1, 13):
            user = User.objects.create_user(
                username=f"demo{i:02d}",
                password="Demo1234!",
                first_name=f"학생{i:02d}",
                email=f"demo{i:02d}@example.com",
            )
            students.append(Student.objects.create(user=user, affiliation="AI Agent", is_active=True))

        # 이전 회차: 자동편성 시드용
        previous, _ = EvaluationRound.objects.update_or_create(
            name="발표용 이전 평가",
            defaults={
                "start_at": now - timedelta(days=14),
                "end_at": now - timedelta(days=13),
                "status": EvaluationRound.Status.ENDED,
                "evaluation_started": False,
                "is_locked": True,
            },
        )
        TeamMembership.objects.filter(team__evaluation_round=previous).delete()
        StudentResult.objects.filter(evaluation_round=previous).delete()
        TeamResult.objects.filter(evaluation_round=previous).delete()
        Team.objects.filter(evaluation_round=previous).delete()

        previous_teams = [
            Team.objects.create(evaluation_round=previous, name=f"{i}팀", is_active=True)
            for i in range(1, 4)
        ]
        for index, student in enumerate(students):
            TeamMembership.objects.create(team=previous_teams[index % 3], student=student)

        previous_scores = [
            Decimal("4.90"), Decimal("4.70"), Decimal("4.55"), Decimal("4.40"),
            Decimal("4.25"), Decimal("4.10"), Decimal("3.95"), Decimal("3.80"),
            Decimal("3.65"), Decimal("3.50"), Decimal("3.35"), Decimal("3.20"),
        ]
        for rank, (student, score) in enumerate(zip(students, previous_scores), start=1):
            StudentResult.objects.create(
                evaluation_round=previous,
                student=student,
                team_score=score,
                personal_score=score,
                base_score=score,
                final_score=score,
                rank=rank,
                is_excluded=False,
            )

        # 현재 회차: 학생 평가 시연용
        current, _ = EvaluationRound.objects.update_or_create(
            name="발표용 현재 평가",
            defaults={
                "start_at": now - timedelta(hours=2),
                "end_at": now + timedelta(days=1),
                "status": EvaluationRound.Status.IN_PROGRESS,
                "evaluation_started": True,
                "is_locked": False,
                "team_weight": 40,
                "personal_weight": 60,
            },
        )

        # 현재 회차 데이터 재생성
        TeamEvaluation.objects.filter(evaluation_round=current).delete()
        PersonalEvaluation.objects.filter(evaluation_round=current).delete()
        StudentResult.objects.filter(evaluation_round=current).delete()
        TeamResult.objects.filter(evaluation_round=current).delete()
        TeamMembership.objects.filter(team__evaluation_round=current).delete()
        Team.objects.filter(evaluation_round=current).delete()
        EvaluationTemplate.objects.filter(evaluation_round=current).delete()
        Assignment.objects.filter(evaluation_round=current).delete()

        Assignment.objects.create(
            evaluation_round=current,
            title="AX 평가 시스템 최종 발표",
            description="발표용 데모 과제입니다. 팀 평가와 개인 평가 흐름을 시연합니다.",
        )

        teams = [
            Team.objects.create(
                evaluation_round=current,
                name=f"{i}팀",
                project_title=f"AX 프로젝트 {i}",
                is_active=True,
            )
            for i in range(1, 4)
        ]
        for index, student in enumerate(students):
            TeamMembership.objects.create(
                team=teams[index // 4],
                student=student,
                is_leader=(index % 4 == 0),
            )

        team_template = EvaluationTemplate.objects.create(
            name="발표용 팀 평가",
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
            evaluation_round=current,
            is_active=True,
        )
        team_criteria = []
        for order, title in enumerate(
            ["요구사항 충족도", "구현 완성도", "발표 이해도"], start=1
        ):
            team_criteria.append(EvaluationCriterion.objects.create(
                template=team_template, title=title, order=order, max_score=5, is_required=True
            ))

        personal_template = EvaluationTemplate.objects.create(
            name="발표용 개인 평가",
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
            evaluation_round=current,
            is_active=True,
        )
        personal_criteria = []
        for order, title in enumerate(
            ["역할 수행", "프로젝트 참여도", "협업 태도"], start=1
        ):
            personal_criteria.append(EvaluationCriterion.objects.create(
                template=personal_template, title=title, order=order, max_score=5, is_required=True
            ))

        # demo01은 발표자가 직접 정상/예외 평가를 보여줄 수 있도록 미평가 상태로 둔다.
        # 나머지 학생들의 평가를 일부 미리 생성해서 관리자 결과 화면도 바로 사용할 수 있게 한다.
        for evaluator in students[1:]:
            own_team = next(
                team for team in teams
                if TeamMembership.objects.filter(team=team, student=evaluator).exists()
            )
            for target_team in teams:
                if target_team.id == own_team.id:
                    continue
                evaluation = TeamEvaluation.objects.create(
                    evaluation_round=current,
                    evaluator=evaluator,
                    target_team=target_team,
                    comment="발표용 자동 생성 팀 평가",
                    is_submitted=True,
                    submitted_at=now,
                )
                base = 4 if target_team.name != "3팀" else 5
                for criterion in team_criteria:
                    TeamEvaluationScore.objects.create(
                        evaluation=evaluation,
                        criterion=criterion,
                        score=base,
                    )

        for team in teams:
            members = [m.student for m in TeamMembership.objects.filter(team=team).select_related("student__user")]
            for evaluator in members:
                if evaluator == students[0]:
                    continue
                for target in members:
                    if target.id == evaluator.id:
                        continue
                    evaluation = PersonalEvaluation.objects.create(
                        evaluation_round=current,
                        evaluator=evaluator,
                        target_student=target,
                        comment="발표용 자동 생성 개인 평가",
                        is_submitted=True,
                        submitted_at=now,
                    )
                    for criterion in personal_criteria:
                        PersonalEvaluationScore.objects.create(
                            evaluation=evaluation,
                            criterion=criterion,
                            score=4,
                        )

        # 결과 공개는 최초 비공개. 관리자 시연에서 공개 버튼을 누르도록 한다.
        ResultPublishSetting.objects.update_or_create(
            evaluation_round=current,
            defaults={
                "is_published": False,
                "show_team_first_place": True,
                "show_all_team_ranks": False,
                "show_personal_score": True,
                "show_overall_rank": True,
                "show_comments": False,
            },
        )

        self.stdout.write(self.style.SUCCESS("✅ 발표용 데모 데이터 생성 완료"))
        self.stdout.write("")
        self.stdout.write("관리자: demo_admin / Demo1234!")
        self.stdout.write("시연 학생: demo01 / Demo1234!")
        self.stdout.write("기타 학생: demo02 ~ demo12 / Demo1234!")
        self.stdout.write("")
        self.stdout.write("권장 시연:")
        self.stdout.write("1) demo01 로그인 → 1팀 확인")
        self.stdout.write("2) 팀 평가 → 자기 팀이 대상에서 빠지는 것 확인 → 2팀 평가")
        self.stdout.write("3) 개인 평가 → 자기 자신/다른 팀원이 대상에 없는 것 확인")
        self.stdout.write("4) demo_admin 로그인 → 결과 화면 진입 → 점수 계산")
        self.stdout.write("5) 결과 공개 설정 → 학생 결과 화면 확인")
        self.stdout.write("6) 새 회차 생성 후 이전 누적 시드 기반 자동 팀 편성 미리보기")
