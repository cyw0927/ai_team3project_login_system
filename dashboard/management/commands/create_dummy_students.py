from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from dashboard.models import (
    Student,
    EvaluationRound,
    Team,
    TeamMembership,
)

from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = "학생 더미데이터 10명 생성"

    def handle(self, *args, **options):

        # 평가 회차 가져오기 / 없으면 생성
        evaluation_round = EvaluationRound.objects.first()

        if not evaluation_round:
            now = timezone.now()

            evaluation_round = EvaluationRound.objects.create(
                name="테스트 평가 회차",
                start_at=now,
                end_at=now + timedelta(days=30),
                status="in_progress",
            )

        # 팀 2개 생성
        teams = []

        for i in range(1, 3):
            team, _ = Team.objects.get_or_create(
                evaluation_round=evaluation_round,
                name=f"{i}팀",
                defaults={
                    "project_title": f"{i}팀 프로젝트",
                    "is_active": True,
                }
            )

            teams.append(team)

        # 학생 10명 생성
        for i in range(1, 11):

            username = f"student{i:02d}"

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": f"학생{i:02d}",
                    "email": f"{username}@test.com",
                }
            )

            if created:
                user.set_password("1234")
                user.save()

            student, _ = Student.objects.get_or_create(
                user=user,
                defaults={
                    "affiliation": "AI",
                    "is_active": True,
                }
            )

            # 5명씩 팀 배정
            team_index = (i - 1) // 5
            team = teams[team_index]

            TeamMembership.objects.get_or_create(
                team=team,
                student=student,
                defaults={
                    "is_leader": (i - 1) % 5 == 0
                }
            )

            self.stdout.write(
                f"{username} 생성 / {team.name} 배정"
            )

        self.stdout.write(
            self.style.SUCCESS("학생 10명 생성 완료!")
        )
