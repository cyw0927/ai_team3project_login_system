from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from dashboard.models import (
    Assignment,
    EvaluationCriterion,
    EvaluationRound,
    EvaluationTemplate,
    Team,
    TeamAssignmentSubmission,
)


PERSONAL_CRITERIA = [
    "역할 수행 및 책임감",
    "프로젝트 기여도",
    "일정 및 약속 준수",
    "의사소통 및 협업",
    "문제 해결 및 적극성",
]

TEAM_CRITERIA = [
    "문제 정의 및 목표의 명확성",
    "요구사항 충족 및 기능 완성도",
    "기술적 설계 및 구현 완성도",
    "AI/AX 활용의 적절성",
    "발표 및 질의응답",
]


class Command(BaseCommand):
    help = (
        "AX2 공식 회차의 팀/개인 평가 템플릿을 5점 척도로 보장하고, "
        "공통 템플릿 라이브러리에도 같은 템플릿을 생성하며, "
        "조별과제와 전 팀 제출 완료 상태를 보정합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--round-name",
            default="AX2 2차 프로젝트",
            help="보정할 평가 회차명 (기본: AX2 2차 프로젝트)",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        round_name = options["round_name"]
        evaluation_round = EvaluationRound.objects.filter(name=round_name).order_by("-id").first()
        if not evaluation_round:
            raise CommandError(f"평가 회차를 찾을 수 없습니다: {round_name}")

        created_templates = 0
        created_criteria = 0

        specs = [
            (
                "AX2 공식 개인동료평가",
                EvaluationTemplate.EvaluationType.PERSONAL,
                PERSONAL_CRITERIA,
            ),
            (
                "AX2 공식 팀평가",
                EvaluationTemplate.EvaluationType.TEAM,
                TEAM_CRITERIA,
            ),
        ]

        # 공통 라이브러리 + 현재 회차 적용 템플릿을 모두 보장한다.
        for template_name, evaluation_type, criterion_titles in specs:
            for template_round in (None, evaluation_round):
                template, created = EvaluationTemplate.objects.get_or_create(
                    name=template_name,
                    evaluation_type=evaluation_type,
                    evaluation_round=template_round,
                    defaults={"is_active": True},
                )
                if created:
                    created_templates += 1
                elif not template.is_active:
                    template.is_active = True
                    template.save(update_fields=["is_active", "updated_at"])

                existing = {criterion.title: criterion for criterion in template.criteria.all()}
                for order, title in enumerate(criterion_titles, start=1):
                    criterion = existing.get(title)
                    if criterion is None:
                        EvaluationCriterion.objects.create(
                            template=template,
                            title=title,
                            description="",
                            order=order,
                            max_score=5,
                            is_required=True,
                        )
                        created_criteria += 1
                        continue

                    changed_fields = []
                    if criterion.order != order:
                        criterion.order = order
                        changed_fields.append("order")
                    if criterion.max_score != 5:
                        criterion.max_score = 5
                        changed_fields.append("max_score")
                    if not criterion.is_required:
                        criterion.is_required = True
                        changed_fields.append("is_required")
                    if changed_fields:
                        changed_fields.append("updated_at")
                        criterion.save(update_fields=changed_fields)

        # 종료 회차라도 관리 명령으로 공식 조별과제를 보정한다.
        assignment, assignment_created = Assignment.objects.get_or_create(
            evaluation_round=evaluation_round,
            assignment_type=Assignment.AssignmentType.TEAM,
            defaults={
                "title": "AX2 2차 프로젝트 조별과제",
                "description": "AX2 공식 익명화 데이터 반영용 조별과제",
            },
        )

        # 현재 회차의 활성 팀을 모두 제출 완료 처리한다.
        teams = list(Team.objects.filter(evaluation_round=evaluation_round, is_active=True).order_by("name"))
        submission_created = 0
        for team in teams:
            _, created = TeamAssignmentSubmission.objects.get_or_create(
                assignment=assignment,
                team=team,
                defaults={
                    "note": "AX2 공식 데이터 기준 제출 완료 처리",
                    "submitted_at": timezone.now(),
                },
            )
            submission_created += int(created)

        total_submissions = TeamAssignmentSubmission.objects.filter(assignment=assignment).count()

        self.stdout.write(self.style.SUCCESS("AX2 회차 마감 보정 완료"))
        self.stdout.write(f"회차: {evaluation_round.name}")
        self.stdout.write(
            f"템플릿: 공통 2개 + 회차 적용 2개 보장 / 신규 템플릿 {created_templates}개"
        )
        self.stdout.write(
            f"평가 문항: 개인 5개 + 팀 5개, 모두 필수·5점 척도 / 신규 문항 {created_criteria}개"
        )
        self.stdout.write(
            f"조별과제: {'신규 생성' if assignment_created else '기존 사용'} / "
            f"팀 제출 {total_submissions}/{len(teams)} (이번 실행 신규 {submission_created}건)"
        )
        self.stdout.write("평가 준비도는 과제/팀/팀 템플릿/개인 템플릿 4개 조건을 모두 충족합니다.")
