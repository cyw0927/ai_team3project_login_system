import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dashboard.models import (
    EvaluationRound,
    PersonalEvaluation,
    TeamEvaluation,
)
from dashboard.views.common import _recalculate_round_results


DUMMY_USERNAME_PATTERN = r"^student[0-9]{2}$"
AUTO_COMMENT = "자동 생성 랜덤 평가"


class Command(BaseCommand):
    help = (
        "seed_random_evaluations 명령으로 생성한 랜덤 평가만 삭제합니다. "
        "실제 사용자가 입력한 평가는 삭제하지 않습니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--round",
            type=int,
            dest="round_id",
            help="평가 회차 ID. 생략하면 최신 회차를 사용합니다.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        evaluation_round = self._get_round(options.get("round_id"))

        team_qs = TeamEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            evaluator__user__username__regex=DUMMY_USERNAME_PATTERN,
            comment=AUTO_COMMENT,
        )

        personal_qs = PersonalEvaluation.objects.filter(
            evaluation_round=evaluation_round,
            evaluator__user__username__regex=DUMMY_USERNAME_PATTERN,
            comment=AUTO_COMMENT,
        )

        team_count = team_qs.count()
        personal_count = personal_qs.count()

        # 연결된 TeamEvaluationScore / PersonalEvaluationScore는
        # FK on_delete=CASCADE 설정에 따라 함께 삭제됩니다.
        team_qs.delete()
        personal_qs.delete()

        _recalculate_round_results(evaluation_round)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("랜덤 평가 데이터 삭제 완료!"))
        self.stdout.write(f"회차: {evaluation_round.id} / {evaluation_round.name}")
        self.stdout.write(f"삭제된 팀 평가: {team_count}건")
        self.stdout.write(f"삭제된 개인 평가: {personal_count}건")
        self.stdout.write(
            self.style.SUCCESS("남아 있는 실제 평가 기준으로 결과 점수를 다시 계산했습니다.")
        )

    def _get_round(self, round_id):
        if round_id:
            try:
                return EvaluationRound.objects.get(pk=round_id)
            except EvaluationRound.DoesNotExist as exc:
                raise CommandError(f"ID={round_id} 평가 회차가 없습니다.") from exc

        evaluation_round = EvaluationRound.objects.order_by("-id").first()
        if not evaluation_round:
            raise CommandError("삭제할 평가 회차가 없습니다.")

        return evaluation_round
