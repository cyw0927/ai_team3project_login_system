from django.core.management.base import BaseCommand
from django.db import transaction

from dashboard.models import EvaluationCriterion, EvaluationTemplate


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
    help = "AX2 CSV 상단 평가 항목을 공통 평가 템플릿 라이브러리에 보장합니다."

    @transaction.atomic
    def handle(self, *args, **options):
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

        for name, evaluation_type, criterion_titles in specs:
            template, created = EvaluationTemplate.objects.get_or_create(
                name=name,
                evaluation_type=evaluation_type,
                evaluation_round=None,
                defaults={"is_active": True},
            )
            if created:
                created_templates += 1
            elif not template.is_active:
                template.is_active = True
                template.save(update_fields=["is_active", "updated_at"])

            existing_by_title = {
                item.title: item
                for item in template.criteria.all()
            }
            for order, title in enumerate(criterion_titles, start=1):
                criterion = existing_by_title.get(title)
                if criterion is None:
                    EvaluationCriterion.objects.create(
                        template=template,
                        title=title,
                        order=order,
                        max_score=5,
                        is_required=True,
                    )
                    created_criteria += 1
                    continue

                changed = False
                if criterion.order != order:
                    criterion.order = order
                    changed = True
                if criterion.max_score != 5:
                    criterion.max_score = 5
                    changed = True
                if not criterion.is_required:
                    criterion.is_required = True
                    changed = True
                if changed:
                    criterion.save(
                        update_fields=["order", "max_score", "is_required", "updated_at"]
                    )

        self.stdout.write(
            self.style.SUCCESS(
                "AX2 템플릿 라이브러리 확인 완료: "
                f"템플릿 신규 {created_templates}개 / 문항 신규 {created_criteria}개"
            )
        )
        self.stdout.write("개인 5문항 + 팀 5문항이 평가 템플릿 화면에 표시됩니다.")
