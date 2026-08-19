import random
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from dashboard.models import (
    EvaluationRound, HRTask, HRTaskStep, Skill, Student, StudentResult,
    StudentSkill, Team, TeamMembership,
)


SURNAMES = [
    "김", "이", "박", "최", "정", "강", "조", "윤", "장", "임",
    "한", "오", "서", "신", "권", "황", "안", "송", "전", "홍",
    "유", "고", "문", "양", "손", "배", "백", "허", "남", "심",
]

GIVEN_FIRST = [
    "민", "서", "지", "수", "도", "하", "예", "윤", "현", "준",
    "성", "태", "주", "채", "시", "재", "은", "유", "승", "정",
]

GIVEN_SECOND = [
    "준", "우", "현", "민", "진", "영", "원", "호", "빈", "혁",
    "아", "연", "은", "윤", "서", "희", "지", "수", "경", "린",
]


class Command(BaseCommand):
    help = "실제 있을 법한 한국식 이름의 더미 수강생을 일괄 생성합니다. 기본 114명."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=114)
        parser.add_argument("--seed", type=int, default=20260819)
        parser.add_argument("--affiliation", type=str, default="")
        parser.add_argument(
            "--with-email",
            action="store_true",
            help="dummyNNN@example.test 형식의 테스트 이메일도 생성합니다.",
        )
        parser.add_argument(
            "--with-sample-data",
            action="store_true",
            help="생성 학생에게 역량점수·팀·과거 성적·성장 과제 데이터를 함께 구성합니다.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        count = max(1, options["count"])
        rng = random.Random(options["seed"])
        affiliation = options["affiliation"].strip()
        with_email = options["with_email"]
        with_sample_data = options["with_sample_data"]

        existing_names = set(
            Student.objects.select_related("user").values_list("user__first_name", flat=True)
        )

        # 충분히 큰 이름 풀을 만든 뒤 중복 없이 섞어서 사용한다.
        pool = [
            f"{surname}{first}{second}"
            for surname in SURNAMES
            for first in GIVEN_FIRST
            for second in GIVEN_SECOND
            if first != second
        ]
        rng.shuffle(pool)

        names = []
        for name in pool:
            if name not in existing_names:
                names.append(name)
            if len(names) >= count:
                break

        if len(names) < count:
            self.stderr.write(self.style.ERROR("중복되지 않는 이름을 충분히 만들지 못했습니다."))
            return

        skills = list(Skill.objects.all())
        created_students = 0
        created_profiles = 0
        generated_students = []

        for index, name in enumerate(names, start=1):
            username = f"dummy_{uuid.uuid4().hex[:16]}"
            email = f"dummy{index:03d}_{uuid.uuid4().hex[:6]}@example.test" if with_email else ""

            user = User(
                username=username,
                email=email,
                first_name=name,
                is_active=True,
            )
            user.set_unusable_password()
            user.save()

            student = Student.objects.create(
                user=user,
                affiliation=affiliation,
                is_active=True,
            )
            created_students += 1
            generated_students.append(student)

            if skills:
                profiles = [
                    StudentSkill(student=student, skill=skill, score=0)
                    for skill in skills
                ]
                StudentSkill.objects.bulk_create(profiles, ignore_conflicts=True)
                created_profiles += len(profiles)

        sample_summary = []
        if with_sample_data and generated_students:
            # 역량점수: 0점 일괄 시작 테스트와 별개로, QA용 분포 확인을 위해 현실적인 범위로 구성.
            if skills:
                for student in generated_students:
                    for skill in skills:
                        StudentSkill.objects.update_or_create(
                            student=student,
                            skill=skill,
                            defaults={
                                "score": rng.randint(15, 85),
                                "note": "초기 진단 및 과제 수행 이력을 반영한 예시 점수",
                            },
                        )
                sample_summary.append(f"역량 프로필 {len(generated_students) * len(skills)}개")

            # 진행 중인 최신 회차가 있으면 팀을 만들어 고르게 배정.
            team_round = (
                EvaluationRound.objects.exclude(status=EvaluationRound.Status.ENDED)
                .order_by("-is_current", "-start_at")
                .first()
            )
            if team_round:
                existing_teams = list(
                    Team.objects.filter(evaluation_round=team_round, is_active=True).order_by("id")
                )
                target_team_count = max(2, round((Student.objects.filter(is_active=True).count()) / 4))
                while len(existing_teams) < target_team_count:
                    team = Team.objects.create(
                        evaluation_round=team_round,
                        name=f"{len(existing_teams) + 1}팀",
                        is_active=True,
                    )
                    existing_teams.append(team)

                for idx, student in enumerate(generated_students):
                    TeamMembership.objects.filter(
                        student=student,
                        team__evaluation_round=team_round,
                    ).delete()
                    TeamMembership.objects.create(
                        team=existing_teams[idx % len(existing_teams)],
                        student=student,
                        is_leader=False,
                        role=rng.choice(["기획", "개발", "데이터", "발표", "문서화"]),
                    )
                sample_summary.append(f"{team_round.name} 팀 배정 {len(generated_students)}명")

            # 최근 종료 회차가 있으면 Seed/결과 화면 성능 테스트용 자연스러운 점수 분포 생성.
            ended_round = (
                EvaluationRound.objects.filter(status=EvaluationRound.Status.ENDED)
                .order_by("-start_at")
                .first()
            )
            if ended_round:
                result_rows = []
                for student in generated_students:
                    team_score = Decimal(str(round(rng.uniform(2.4, 4.8), 2)))
                    personal_score = Decimal(str(round(rng.uniform(2.2, 4.9), 2)))
                    final_score = (
                        team_score * Decimal(ended_round.team_weight)
                        + personal_score * Decimal(ended_round.personal_weight)
                    ) / Decimal(100)
                    result, _ = StudentResult.objects.update_or_create(
                        evaluation_round=ended_round,
                        student=student,
                        defaults={
                            "team_score": team_score,
                            "personal_score": personal_score,
                            "base_score": final_score,
                            "final_score": final_score,
                            "is_excluded": False,
                        },
                    )
                    result_rows.append(result)
                ordered = list(
                    StudentResult.objects.filter(
                        evaluation_round=ended_round,
                        is_excluded=False,
                    ).order_by("-final_score", "student_id")
                )
                for rank, result in enumerate(ordered, start=1):
                    if result.rank != rank:
                        result.rank = rank
                        result.save(update_fields=["rank", "updated_at"])
                sample_summary.append(f"{ended_round.name} 성적 {len(result_rows)}건")

            # 개별 역량 과제: 다양한 상태/진행률을 확인할 수 있게 일부 학생에게만 생성.
            task_titles = [
                "데이터 전처리 실습", "REST API 설계", "SQL 집계 쿼리", "발표 자료 구조화",
                "사용자 요구사항 분석", "Django 모델링", "Git 협업 실습", "테스트 케이스 작성",
                "대시보드 시각화", "프로젝트 회고 정리", "Python 함수 리팩터링", "ERD 검토",
            ]
            task_count = min(24, len(generated_students))
            for idx, student in enumerate(generated_students[:task_count]):
                status_cycle = [
                    HRTask.Status.SCHEDULED,
                    HRTask.Status.IN_PROGRESS,
                    HRTask.Status.REVIEW,
                    HRTask.Status.COMPLETED,
                ]
                task = HRTask.objects.create(
                    title=task_titles[idx % len(task_titles)],
                    description="학습 내용을 실제 프로젝트 상황에 적용해 결과와 근거를 정리합니다.",
                    assignee=student,
                    start_date=timezone.localdate() - timedelta(days=rng.randint(0, 7)),
                    due_date=timezone.localdate() + timedelta(days=rng.randint(1, 14)),
                    status=status_cycle[idx % len(status_cycle)],
                    priority=rng.choice([
                        HRTask.Priority.LOW, HRTask.Priority.NORMAL, HRTask.Priority.HIGH
                    ]),
                )
                completed_steps = idx % 4
                for step_no, step_title in enumerate(
                    ["요구사항 확인", "작업 수행", "결과 검토"], start=1
                ):
                    HRTaskStep.objects.create(
                        task=task,
                        title=step_title,
                        detail=f"{step_title} 단계에서 확인해야 할 핵심 내용을 정리합니다.",
                        order=step_no,
                        is_completed=step_no <= completed_steps,
                        completed_at=timezone.now() if step_no <= completed_steps else None,
                    )
            sample_summary.append(f"역량 과제 {task_count}개")

        total_students = Student.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"더미 수강생 {created_students}명 생성 완료. "
                f"공통 역량 프로필 {created_profiles}개 생성. "
                f"현재 전체 수강생: {total_students}명"
                + (f" / 추가 샘플: {', '.join(sample_summary)}" if sample_summary else "")
            )
        )
