import random
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from dashboard.models import (
    EvaluationCriterion,
    EvaluationRound,
    EvaluationTemplate,
    PersonalEvaluation,
    PersonalEvaluationScore,
    RoundAttendance,
    Student,
    Team,
    TeamEvaluation,
    TeamEvaluationScore,
    TeamMembership,
)
from dashboard.views.common import _recalculate_round_results


DUMMY_USERNAME_PATTERN = re.compile(r"^student\d{2}$")


class Command(BaseCommand):
    help = (
        "student01~student99 형식의 더미 학생이 아직 제출하지 않은 팀/개인 평가를 "
        "랜덤 점수로 자동 생성합니다. 기존 제출 평가는 수정하지 않습니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--round",
            type=int,
            dest="round_id",
            help="평가 회차 ID. 생략하면 현재 진행 중이며 평가가 시작된 최신 회차를 사용합니다.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="같은 랜덤 결과를 재현할 때 사용할 seed 값입니다. 예: --seed 42",
        )
        parser.add_argument(
            "--min-score",
            type=int,
            default=1,
            help="랜덤 최소 점수(기본 1)",
        )
        parser.add_argument(
            "--max-score",
            type=int,
            default=5,
            help="랜덤 최대 점수(기본 5)",
        )
        parser.add_argument(
            "--include-existing-drafts",
            action="store_true",
            help="기존 임시저장 평가도 랜덤 점수로 채워 최종 제출합니다. 기본값은 기존 평가 레코드 자체를 건드리지 않습니다.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["seed"] is not None:
            random.seed(options["seed"])

        min_score = options["min_score"]
        max_score = options["max_score"]
        if min_score < 1 or max_score > 5 or min_score > max_score:
            raise CommandError("점수 범위는 1~5 안에서 지정해야 합니다. 예: --min-score 2 --max-score 5")

        evaluation_round = self._get_round(options.get("round_id"))

        if not evaluation_round.evaluation_started:
            raise CommandError(
                f"'{evaluation_round.name}' 회차는 아직 평가 시작 전입니다. 관리자에서 평가 시작 후 실행하세요."
            )
        if evaluation_round.is_locked:
            raise CommandError(
                f"'{evaluation_round.name}' 회차는 현재 평가 중단 상태입니다. 평가 재개 후 실행하세요."
            )

        team_template = (
            EvaluationTemplate.objects.filter(
                evaluation_round=evaluation_round,
                evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
                is_active=True,
            )
            .prefetch_related("criteria")
            .first()
        )
        personal_template = (
            EvaluationTemplate.objects.filter(
                evaluation_round=evaluation_round,
                evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
                is_active=True,
            )
            .prefetch_related("criteria")
            .first()
        )

        if not team_template:
            raise CommandError("현재 회차에 적용된 활성 팀 평가 템플릿이 없습니다.")
        if not personal_template:
            raise CommandError("현재 회차에 적용된 활성 개인 평가 템플릿이 없습니다.")

        team_criteria = list(team_template.criteria.all().order_by("order", "id"))
        personal_criteria = list(personal_template.criteria.all().order_by("order", "id"))
        if not team_criteria:
            raise CommandError("팀 평가 템플릿에 평가 문항이 없습니다.")
        if not personal_criteria:
            raise CommandError("개인 평가 템플릿에 평가 문항이 없습니다.")

        memberships = list(
            TeamMembership.objects.filter(team__evaluation_round=evaluation_round)
            .select_related("student__user", "team")
            .order_by("student__user__username")
        )
        student_team = {membership.student_id: membership.team for membership in memberships}

        dummy_students = [
            membership.student
            for membership in memberships
            if membership.student.is_active
            and membership.student.user.is_active
            and DUMMY_USERNAME_PATTERN.fullmatch(membership.student.user.username or "")
        ]

        # 같은 학생이 중복 membership queryset에 잡히더라도 한 번만 처리
        dummy_students = list({student.id: student for student in dummy_students}.values())
        dummy_students.sort(key=lambda s: s.user.username)

        if not dummy_students:
            raise CommandError(
                "현재 회차 팀에 student01 같은 형식의 더미 학생이 없습니다. "
                "create_dummy_students 실행 여부와 팀 배정을 확인하세요."
            )

        active_teams = list(
            Team.objects.filter(evaluation_round=evaluation_round, is_active=True).order_by("name")
        )

        created_team = 0
        skipped_team = 0
        created_personal = 0
        skipped_personal = 0

        for evaluator in dummy_students:
            my_team = student_team.get(evaluator.id)
            if not my_team:
                continue

            attendance = RoundAttendance.objects.filter(
                evaluation_round=evaluation_round,
                student=evaluator,
            ).first()
            team_eval_blocked = bool(
                attendance
                and attendance.status
                in {RoundAttendance.Status.ABSENT, RoundAttendance.Status.EXCUSED}
            )

            # BR-01: 자기 팀은 평가하지 않는다.
            if not team_eval_blocked:
                for target_team in active_teams:
                    if target_team.id == my_team.id:
                        continue

                    existing = TeamEvaluation.objects.filter(
                        evaluation_round=evaluation_round,
                        evaluator=evaluator,
                        target_team=target_team,
                    ).first()

                    if existing and (existing.is_submitted or not options["include_existing_drafts"]):
                        skipped_team += 1
                        continue

                    evaluation = existing or TeamEvaluation.objects.create(
                        evaluation_round=evaluation_round,
                        evaluator=evaluator,
                        target_team=target_team,
                    )
                    evaluation.comment = "자동 생성 랜덤 평가"
                    evaluation.is_submitted = True
                    evaluation.submitted_at = timezone.now()
                    evaluation.save()

                    self._fill_scores(
                        evaluation=evaluation,
                        score_model=TeamEvaluationScore,
                        criteria=team_criteria,
                        min_score=min_score,
                        max_score=max_score,
                    )
                    created_team += 1

            # BR-02~04: 같은 팀원만, 자기 자신 제외.
            teammates = (
                Student.objects.filter(
                    team_memberships__team=my_team,
                    is_active=True,
                    user__is_active=True,
                )
                .exclude(pk=evaluator.pk)
                .select_related("user")
                .distinct()
            )

            for target_student in teammates:
                existing = PersonalEvaluation.objects.filter(
                    evaluation_round=evaluation_round,
                    evaluator=evaluator,
                    target_student=target_student,
                ).first()

                if existing and (existing.is_submitted or not options["include_existing_drafts"]):
                    skipped_personal += 1
                    continue

                evaluation = existing or PersonalEvaluation.objects.create(
                    evaluation_round=evaluation_round,
                    evaluator=evaluator,
                    target_student=target_student,
                )
                evaluation.comment = "자동 생성 랜덤 평가"
                evaluation.is_submitted = True
                evaluation.submitted_at = timezone.now()
                evaluation.save()

                self._fill_scores(
                    evaluation=evaluation,
                    score_model=PersonalEvaluationScore,
                    criteria=personal_criteria,
                    min_score=min_score,
                    max_score=max_score,
                )
                created_personal += 1

        _recalculate_round_results(evaluation_round)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("랜덤 평가 데이터 생성 완료!"))
        self.stdout.write(f"회차: {evaluation_round.id} / {evaluation_round.name}")
        self.stdout.write(f"대상 더미 학생: {len(dummy_students)}명")
        self.stdout.write(f"팀 평가 생성: {created_team}건 / 기존 데이터 건너뜀: {skipped_team}건")
        self.stdout.write(f"개인 평가 생성: {created_personal}건 / 기존 데이터 건너뜀: {skipped_personal}건")
        self.stdout.write(
            self.style.SUCCESS("결과 점수와 순위까지 다시 계산했습니다.")
        )

    def _get_round(self, round_id):
        if round_id:
            try:
                return EvaluationRound.objects.get(pk=round_id)
            except EvaluationRound.DoesNotExist as exc:
                raise CommandError(f"ID={round_id} 평가 회차가 없습니다.") from exc

        evaluation_round = (
            EvaluationRound.objects.filter(
                status=EvaluationRound.Status.IN_PROGRESS,
                evaluation_started=True,
            )
            .order_by("-start_at")
            .first()
        )
        if not evaluation_round:
            raise CommandError(
                "평가가 시작된 진행 중 회차가 없습니다. --round 회차ID를 지정하거나 관리자에서 평가를 시작하세요."
            )
        return evaluation_round

    @staticmethod
    def _fill_scores(evaluation, score_model, criteria, min_score, max_score):
        for criterion in criteria:
            criterion_max = max(1, min(5, int(criterion.max_score)))
            low = min(min_score, criterion_max)
            high = min(max_score, criterion_max)
            if low > high:
                low = high

            score_model.objects.update_or_create(
                evaluation=evaluation,
                criterion=criterion,
                defaults={"score": random.randint(low, high)},
            )
