from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from dashboard.models import (
    Announcement,
    Assignment,
    EvaluationCriterion,
    EvaluationRound,
    EvaluationTemplate,
    ResultPublishSetting,
    RoundAttendance,
    Student,
    StudentResult,
    Team,
    TeamAssignmentSubmission,
    TeamMembership,
    TeamResult,
)


class Command(BaseCommand):
    help = "관리자 1명 + 학생 30명 + 이전 회차 점수 + Z식 편성용 다음 회차를 생성합니다."

    @transaction.atomic
    def handle(self, *args, **options):
        # -------------------------------------------------
        # 0. 관리자 계정
        # -------------------------------------------------
        admin, _ = User.objects.get_or_create(username="admin01")
        admin.first_name = "관리자테스트"
        admin.last_name = ""
        admin.email = "admin01@example.com"
        admin.is_active = True
        admin.is_staff = True
        admin.is_superuser = True
        admin.set_password("admin1234!")
        admin.save()

        # -------------------------------------------------
        # 1. 이전에 우리가 만든 데모 학생 계정 정리
        #    실제 사용자가 직접 만든 계정은 건드리지 않음
        # -------------------------------------------------
        demo_usernames = ["test01"]
        demo_usernames += [f"score{i:02d}" for i in range(2, 9)]
        demo_usernames += [f"student{i:02d}" for i in range(1, 31)]

        User.objects.filter(username__in=demo_usernames).delete()

        # -------------------------------------------------
        # 2. 학생 30명 생성
        # -------------------------------------------------
        names = [
            "김민수", "이서연", "박지훈", "정다라", "김서준",
            "이하윤", "박도윤", "최지우", "정현우", "강서연",
            "조민재", "윤지민", "장서준", "임수빈", "한도현",
            "오예린", "송민준", "신채원", "권지훈", "홍서윤",
            "문현우", "배지민", "백도윤", "유하린", "남민재",
            "노서연", "황지훈", "안채원", "서현우", "전유진",
        ]

        students = []
        for i, name in enumerate(names, start=1):
            username = f"student{i:02d}"
            email = f"student{i:02d}@example.com"

            # 기존 계정이 남아 있어도 터지지 않도록 재사용/갱신
            user, _ = User.objects.get_or_create(username=username)
            user.email = email
            user.first_name = name
            user.last_name = ""
            user.is_active = True
            user.set_password("test1234!")
            user.save()

            student, _ = Student.objects.update_or_create(
                user=user,
                defaults={
                    "affiliation": "AI Agent",
                    "is_active": True,
                },
            )
            students.append(student)

        # -------------------------------------------------
        # 3. 이전 회차 생성: 성적/시드가 존재하는 회차
        # -------------------------------------------------
        round1_start = timezone.make_aware(datetime(2026, 8, 1, 9, 0))
        round1_end = timezone.make_aware(datetime(2026, 8, 7, 17, 0))

        round1, _ = EvaluationRound.objects.update_or_create(
            name="더미 1차 평가",
            defaults={
                "start_at": round1_start,
                "end_at": round1_end,
                "status": EvaluationRound.Status.ENDED,
                "is_reopened": False,
                "seed_weight": 100,
            },
        )

        # 기존 같은 회차의 팀/결과를 재실행 가능하도록 정리
        TeamMembership.objects.filter(team__evaluation_round=round1).delete()
        StudentResult.objects.filter(evaluation_round=round1).delete()
        TeamResult.objects.filter(evaluation_round=round1).delete()
        Team.objects.filter(evaluation_round=round1).delete()

        # -------------------------------------------------
        # 4. 이전 회차 6팀 × 5명
        # -------------------------------------------------
        team_scores = [
            Decimal("4.90"),
            Decimal("4.75"),
            Decimal("4.60"),
            Decimal("4.45"),
            Decimal("4.30"),
            Decimal("4.15"),
        ]

        teams = []
        for i in range(6):
            team = Team.objects.create(
                evaluation_round=round1,
                name=f"{i + 1}팀",
                project_title=f"더미 프로젝트 {i + 1}",
                is_active=True,
            )
            teams.append(team)

        for index, student in enumerate(students):
            team_index = index % 6
            TeamMembership.objects.create(
                team=teams[team_index],
                student=student,
            )

        # -------------------------------------------------
        # 5. 개인점수 + 팀점수 + 최종점수 생성
        #    최종 = 개인 60% + 팀 40%
        # -------------------------------------------------
        results = []

        # 30명 모두 점수가 다르게 나오도록 개인점수를 완만하게 감소
        for index, student in enumerate(students):
            team_index = index % 6
            personal_score = (
                Decimal("4.98") - Decimal(index) * Decimal("0.08")
            ).quantize(Decimal("0.01"))

            # 혹시 1점 미만이 되지 않도록 방어
            if personal_score < Decimal("1.00"):
                personal_score = Decimal("1.00")

            team_score = team_scores[team_index]
            final_score = (
                personal_score * Decimal("0.60")
                + team_score * Decimal("0.40")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            result = StudentResult.objects.create(
                evaluation_round=round1,
                student=student,
                team_score=team_score,
                personal_score=personal_score,
                final_score=final_score,
                is_excluded=False,
            )
            results.append(result)

        # 최종점수 내림차순, 동점이면 개인점수 높은 순
        results.sort(
            key=lambda result: (
                result.final_score,
                result.personal_score,
                -result.student_id,
            ),
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
            result.save(update_fields=["rank", "updated_at"])

        # 팀 순위
        ordered_teams = sorted(
            zip(teams, team_scores),
            key=lambda item: item[1],
            reverse=True,
        )
        for rank, (team, score) in enumerate(ordered_teams, start=1):
            TeamResult.objects.create(
                evaluation_round=round1,
                team=team,
                score=score,
                rank=rank,
                is_excluded=False,
            )

        # -------------------------------------------------
        # 6. 결과 공개 설정
        #    학생 result 화면에서 과거 성적/평균/추이를 바로 확인할 수 있게 한다.
        # -------------------------------------------------
        ResultPublishSetting.objects.update_or_create(
            evaluation_round=round1,
            defaults={
                "is_published": True,
                "show_team_first_place": True,
                "show_all_team_ranks": True,
                "show_personal_score": True,
                "show_overall_rank": True,
                "show_comments": True,
            },
        )

        # -------------------------------------------------
        # 7. 현재 진행 중인 2차 평가
        #    학생/관리자 UI를 실제 데이터가 채워진 상태로 시연하기 위한 회차.
        # -------------------------------------------------
        round2_start = timezone.make_aware(datetime(2026, 8, 14, 9, 0))
        round2_end = timezone.make_aware(datetime(2026, 8, 20, 17, 0))

        round2, _ = EvaluationRound.objects.update_or_create(
            name="더미 2차 평가",
            defaults={
                "start_at": round2_start,
                "end_at": round2_end,
                "status": EvaluationRound.Status.IN_PROGRESS,
                "is_reopened": False,
                "is_locked": False,
                "evaluation_started": False,
                "team_weight": 40,
                "personal_weight": 60,
                "seed_weight": 100,
                "seed_team_weight": 40,
                "seed_personal_weight": 60,
            },
        )

        TeamAssignmentSubmission.objects.filter(
            assignment__evaluation_round=round2
        ).delete()
        RoundAttendance.objects.filter(evaluation_round=round2).delete()
        TeamMembership.objects.filter(team__evaluation_round=round2).delete()
        Team.objects.filter(evaluation_round=round2).delete()
        EvaluationTemplate.objects.filter(evaluation_round=round2).delete()
        Assignment.objects.filter(evaluation_round=round2).delete()

        # 과제
        assignment2 = Assignment.objects.create(
            evaluation_round=round2,
            title="AI Agent 서비스 프로토타입",
            description=(
                "팀별로 사용자 문제를 정의하고 Django 기반 서비스 프로토타입을 구현합니다. "
                "발표 자료와 실행 가능한 결과물을 제출하세요."
            ),
        )

        # 2차 팀 6개 × 5명: 1차 성적 순위를 기준으로 Z식(스네이크) 배치
        round2_teams = [
            Team.objects.create(
                evaluation_round=round2,
                name=f"{i}팀",
                project_title=[
                    "AI 학습 코치",
                    "고객 문의 자동화",
                    "채용 지원 에이전트",
                    "여행 플래너",
                    "문서 분석 비서",
                    "평가 운영 자동화",
                ][i - 1],
                is_active=True,
            )
            for i in range(1, 7)
        ]

        sorted_students = [result.student for result in results]
        snake_team_indexes = []
        while len(snake_team_indexes) < len(sorted_students):
            snake_team_indexes.extend(range(6))
            snake_team_indexes.extend(range(5, -1, -1))
        snake_team_indexes = snake_team_indexes[: len(sorted_students)]

        for index, student in enumerate(sorted_students):
            team = round2_teams[snake_team_indexes[index]]
            TeamMembership.objects.create(
                team=team,
                student=student,
                is_leader=(not TeamMembership.objects.filter(team=team).exists()),
            )

        # 일부 팀은 과제 제출 완료 상태로 만들어 제출/미제출 UI를 동시에 확인
        for team in round2_teams[:3]:
            leader = (
                TeamMembership.objects.filter(team=team, is_leader=True)
                .select_related("student")
                .first()
            )
            TeamAssignmentSubmission.objects.create(
                assignment=assignment2,
                team=team,
                submitted_by=leader.student if leader else None,
                submission_url=f"https://example.com/demo/{team.id}",
                note=f"{team.name} 데모 제출물입니다.",
                submitted_at=timezone.now(),
            )

        # 팀/개인 평가 템플릿
        team_template = EvaluationTemplate.objects.create(
            name="2차 팀 평가 기본 템플릿",
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
            evaluation_round=round2,
            is_active=True,
        )
        for order, (title, desc) in enumerate(
            [
                ("문제 정의", "해결하려는 문제와 사용자 요구가 명확한가"),
                ("완성도", "서비스가 안정적으로 동작하고 결과물이 완성되었는가"),
                ("발표", "핵심 기능과 결과를 이해하기 쉽게 전달했는가"),
            ],
            start=1,
        ):
            EvaluationCriterion.objects.create(
                template=team_template,
                title=title,
                description=desc,
                order=order,
                max_score=5,
                is_required=True,
            )

        personal_template = EvaluationTemplate.objects.create(
            name="2차 개인 평가 기본 템플릿",
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
            evaluation_round=round2,
            is_active=True,
        )
        for order, (title, desc) in enumerate(
            [
                ("기여도", "팀 결과물에 실질적으로 기여했는가"),
                ("협업", "의사소통과 역할 수행이 원활했는가"),
                ("책임감", "정해진 일정과 역할을 책임감 있게 수행했는가"),
            ],
            start=1,
        ):
            EvaluationCriterion.objects.create(
                template=personal_template,
                title=title,
                description=desc,
                order=order,
                max_score=5,
                is_required=True,
            )

        # 발표 당일 출결: 기본은 출석, 한 명 결석/한 명 공결
        for student in students:
            status = RoundAttendance.Status.PRESENT
            note = ""
            if student == students[3]:
                status = RoundAttendance.Status.ABSENT
                note = "데모 결석"
            elif student == students[8]:
                status = RoundAttendance.Status.EXCUSED
                note = "데모 공결"
            RoundAttendance.objects.create(
                evaluation_round=round2,
                student=student,
                status=status,
                note=note,
            )

        # -------------------------------------------------
        # 8. 다음 자동편성 테스트용 3차 회차
        #    팀을 비워둬 Z식 자동편성 미리보기/확정을 테스트한다.
        # -------------------------------------------------
        round3_start = timezone.make_aware(datetime(2026, 8, 27, 9, 0))
        round3_end = timezone.make_aware(datetime(2026, 9, 2, 17, 0))

        round3, _ = EvaluationRound.objects.update_or_create(
            name="더미 3차 평가",
            defaults={
                "start_at": round3_start,
                "end_at": round3_end,
                "status": EvaluationRound.Status.SCHEDULED,
                "is_reopened": False,
                "is_locked": False,
                "evaluation_started": False,
                "team_weight": 40,
                "personal_weight": 60,
                "seed_weight": 100,
                "seed_team_weight": 40,
                "seed_personal_weight": 60,
            },
        )
        TeamMembership.objects.filter(team__evaluation_round=round3).delete()
        Team.objects.filter(evaluation_round=round3).delete()
        Assignment.objects.filter(evaluation_round=round3).delete()

        Assignment.objects.create(
            evaluation_round=round3,
            title="최종 AI Agent 프로젝트",
            description="이전 회차의 누적 Seed를 활용하여 새 팀을 편성한 뒤 최종 프로젝트를 수행합니다.",
        )

        # -------------------------------------------------
        # 9. 공지사항
        # -------------------------------------------------
        Announcement.objects.filter(
            title__startswith="[DEMO]"
        ).delete()
        Announcement.objects.create(
            title="[DEMO] 2차 평가 운영 안내",
            body="과제 제출은 평가 시작 전까지 수정할 수 있습니다. 평가 시작 후에는 팀 평가를 먼저 진행합니다.",
            priority=Announcement.Priority.IMPORTANT,
            is_published=True,
            created_by=admin,
        )
        Announcement.objects.create(
            title="[DEMO] 발표 당일 출결 확인",
            body="결석·공결 학생은 팀 평가가 면제되지만 같은 팀원 개인 평가는 참여할 수 있습니다.",
            priority=Announcement.Priority.NORMAL,
            is_published=True,
            created_by=admin,
        )
        Announcement.objects.create(
            title="[DEMO] 다음 회차 자동 팀 편성",
            body="2차 평가 종료 후 누적 Seed를 활용해 3차 팀을 자동 편성할 수 있습니다.",
            priority=Announcement.Priority.NORMAL,
            is_published=True,
            created_by=admin,
        )

        # -------------------------------------------------
        # 10. 결과 출력
        # -------------------------------------------------
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("✅ 데모 데이터 생성 완료"))
        self.stdout.write("관리자: admin01 / admin1234!")
        self.stdout.write("학생: student01 ~ student30 / test1234!")
        self.stdout.write("")
        self.stdout.write("[시연용 데이터]")
        self.stdout.write("1차: 종료 + 점수/순위 + 결과 공개")
        self.stdout.write("2차: 진행 중 + 6팀 + 과제 + 템플릿 + 출결 + 일부 제출")
        self.stdout.write("3차: 시작 전 + 팀 미편성 (자동편성 테스트용)")
        self.stdout.write("공지: DEMO 공지 3건")
        self.stdout.write("")
        self.stdout.write("[더미 1차 평가 순위]")

        for result in results:
            self.stdout.write(
                f"{result.rank:02d}위  {result.student.name:<8} "
                f"| 개인 {result.personal_score:.2f} "
                f"| 팀 {result.team_score:.2f} "
                f"| 최종 {result.final_score:.2f}"
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("시연 순서"))
        self.stdout.write("1) 관리자 로그인 → 관리자 홈/수강생/회차/과제/팀/결과 확인")
        self.stdout.write("2) 학생 student01 로그인 → 홈/팀/과제/결과 확인")
        self.stdout.write("3) 관리자 → 팀 편성 → 더미 3차 평가 → 자동 팀 편성 미리보기")
        self.stdout.write("4) 관리자 → 더미 2차 평가 → 평가 시작 후 학생 평가 화면 확인")
