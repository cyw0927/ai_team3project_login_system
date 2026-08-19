from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from dashboard.models import (
    EvaluationRound,
    Student,
    StudentResult,
    Team,
    TeamMembership,
    TeamResult,
)


class Command(BaseCommand):
    help = "Z식 자동편성 테스트용 수강생/팀/점수 더미 데이터를 생성합니다."

    @transaction.atomic
    def handle(self, *args, **options):
        # 현재 프로젝트의 예시 회차(8/13)보다 앞선 회차로 만들어
        # 다음 회차의 Z식 시드 데이터로 사용할 수 있게 합니다.
        start_at = timezone.make_aware(datetime(2026, 8, 1, 9, 0))
        end_at = timezone.make_aware(datetime(2026, 8, 7, 17, 0))

        evaluation_round, _ = EvaluationRound.objects.update_or_create(
            name="더미 성적 테스트 회차",
            defaults={
                "start_at": start_at,
                "end_at": end_at,
                "status": EvaluationRound.Status.ENDED,
                "is_reopened": False,
            },
        )

        team_specs = [
            ("1팀", Decimal("4.80")),
            ("2팀", Decimal("4.60")),
            ("3팀", Decimal("4.40")),
            ("4팀", Decimal("4.20")),
        ]

        teams = []
        for team_name, team_score in team_specs:
            team, _ = Team.objects.update_or_create(
                evaluation_round=evaluation_round,
                name=team_name,
                defaults={
                    "project_title": f"{team_name} 테스트 프로젝트",
                    "is_active": True,
                },
            )
            teams.append((team, team_score))

        # 이름, username, 개인점수, 소속팀 index
        # 최종점수 = 개인점수 60% + 팀점수 40%
        student_specs = [
            ("김테스트", "test01", Decimal("4.95"), 0),
            ("이테스트", "score02", Decimal("4.85"), 1),
            ("박테스트", "score03", Decimal("4.75"), 2),
            ("최테스트", "score04", Decimal("4.65"), 3),
            ("정테스트", "score05", Decimal("4.45"), 3),
            ("강테스트", "score06", Decimal("4.35"), 2),
            ("윤테스트", "score07", Decimal("4.25"), 1),
            ("한테스트", "score08", Decimal("4.15"), 0),
        ]

        results = []
        for name, username, personal_score, team_index in student_specs:
            email = f"{username}@example.com"
            user, _ = User.objects.get_or_create(username=username)
            user.first_name = name
            user.last_name = ""
            user.email = email
            user.is_active = True
            user.is_staff = False
            user.is_superuser = False
            user.set_password("test1234!")
            user.save()

            student, _ = Student.objects.update_or_create(
                user=user,
                defaults={"affiliation": "AI Agent", "is_active": True},
            )

            team, team_score = teams[team_index]
            TeamMembership.objects.filter(
                student=student,
                team__evaluation_round=evaluation_round,
            ).delete()
            TeamMembership.objects.create(team=team, student=student)

            final_score = (
                personal_score * Decimal("0.60")
                + team_score * Decimal("0.40")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            result, _ = StudentResult.objects.update_or_create(
                evaluation_round=evaluation_round,
                student=student,
                defaults={
                    "team_score": team_score,
                    "personal_score": personal_score,
                    "final_score": final_score,
                    "is_excluded": False,
                },
            )
            results.append(result)

        # 최종점수 내림차순, 동점이면 개인점수 높은 순
        results.sort(
            key=lambda r: (r.final_score, r.personal_score),
            reverse=True,
        )
        previous_key = None
        current_rank = 0
        for index, result in enumerate(results, start=1):
            key = (result.final_score, result.personal_score)
            if key != previous_key:
                current_rank = index
                previous_key = key
            result.rank = current_rank
            result.is_excluded = False
            result.save(update_fields=["rank", "is_excluded", "updated_at"])

        # 팀 결과도 테스트 화면에서 바로 보이도록 저장
        ordered_teams = sorted(teams, key=lambda item: item[1], reverse=True)
        for rank, (team, team_score) in enumerate(ordered_teams, start=1):
            TeamResult.objects.update_or_create(
                evaluation_round=evaluation_round,
                team=team,
                defaults={
                    "score": team_score,
                    "rank": rank,
                    "is_excluded": False,
                },
            )

        self.stdout.write(self.style.SUCCESS("더미 점수 데이터 생성 완료"))
        self.stdout.write(f"회차: {evaluation_round.name}")
        self.stdout.write("공통 비밀번호: test1234!")
        self.stdout.write("")
        self.stdout.write("순위 / 학생 / 개인점수 / 팀점수 / 최종점수")
        for result in results:
            self.stdout.write(
                f"{result.rank:>2}위  {result.student.name:<8}  "
                f"{result.personal_score:.2f} / {result.team_score:.2f} / {result.final_score:.2f}"
            )
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "최종점수는 개인 60% + 팀 40%이며, 다음 회차 자동편성에서 Z식 시드로 사용할 수 있습니다."
            )
        )
