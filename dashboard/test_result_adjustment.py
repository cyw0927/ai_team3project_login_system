from decimal import Decimal
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    EvaluationCriterion,
    EvaluationRound,
    EvaluationTemplate,
    PersonalEvaluation,
    PersonalEvaluationScore,
    Student,
    StudentResult,
    Team,
    TeamEvaluation,
    TeamEvaluationScore,
    TeamMembership,
)
from .services.result_service import _recalculate_round_results


class ResultAdjustmentRecalculationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.round = EvaluationRound.objects.create(
            name="보정점수 테스트",
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=1),
            status=EvaluationRound.Status.IN_PROGRESS,
            evaluation_started=True,
            team_weight=40,
            personal_weight=60,
        )

        cls.admin = User.objects.create_user(
            username="adjust_admin",
            password="test1234!",
            is_staff=True,
        )

        cls.students = []
        for index in range(4):
            user = User.objects.create_user(
                username=f"adjust_student_{index}",
                password="test1234!",
                first_name=f"학생{index + 1}",
            )
            cls.students.append(Student.objects.create(user=user))

        cls.team1 = Team.objects.create(
            evaluation_round=cls.round,
            name="1팀",
            is_active=True,
        )
        cls.team2 = Team.objects.create(
            evaluation_round=cls.round,
            name="2팀",
            is_active=True,
        )
        for student in cls.students[:2]:
            TeamMembership.objects.create(team=cls.team1, student=student)
        for student in cls.students[2:]:
            TeamMembership.objects.create(team=cls.team2, student=student)

        cls.team_template = EvaluationTemplate.objects.create(
            name="팀 평가",
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
            evaluation_round=cls.round,
            is_active=True,
        )
        cls.team_criterion = EvaluationCriterion.objects.create(
            template=cls.team_template,
            title="완성도",
            order=1,
            max_score=5,
        )

        cls.personal_template = EvaluationTemplate.objects.create(
            name="개인 평가",
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
            evaluation_round=cls.round,
            is_active=True,
        )
        cls.personal_criterion = EvaluationCriterion.objects.create(
            template=cls.personal_template,
            title="협업",
            order=1,
            max_score=5,
        )

        # 모든 평가자가 필수 평가 대상을 전부 제출하도록 구성한다.
        for evaluator in cls.students[:2]:
            team_eval = TeamEvaluation.objects.create(
                evaluation_round=cls.round,
                evaluator=evaluator,
                target_team=cls.team2,
                is_submitted=True,
                submitted_at=timezone.now(),
            )
            TeamEvaluationScore.objects.create(
                evaluation=team_eval,
                criterion=cls.team_criterion,
                score=4,
            )

        for evaluator in cls.students[2:]:
            team_eval = TeamEvaluation.objects.create(
                evaluation_round=cls.round,
                evaluator=evaluator,
                target_team=cls.team1,
                is_submitted=True,
                submitted_at=timezone.now(),
            )
            TeamEvaluationScore.objects.create(
                evaluation=team_eval,
                criterion=cls.team_criterion,
                score=4,
            )

        peer_pairs = [
            (cls.students[0], cls.students[1]),
            (cls.students[1], cls.students[0]),
            (cls.students[2], cls.students[3]),
            (cls.students[3], cls.students[2]),
        ]
        for evaluator, target in peer_pairs:
            personal_eval = PersonalEvaluation.objects.create(
                evaluation_round=cls.round,
                evaluator=evaluator,
                target_student=target,
                is_submitted=True,
                submitted_at=timezone.now(),
            )
            PersonalEvaluationScore.objects.create(
                evaluation=personal_eval,
                criterion=cls.personal_criterion,
                score=5,
            )

    def setUp(self):
        _recalculate_round_results(self.round)

    def test_recalculation_preserves_adjustment_and_applies_to_final_score(self):
        result = StudentResult.objects.get(
            evaluation_round=self.round,
            student=self.students[0],
        )
        self.assertEqual(result.base_score, Decimal("4.6"))

        result.adjustment_score = Decimal("0.50")
        result.adjustment_reason = "발표 기여도 반영"
        result.save(update_fields=["adjustment_score", "adjustment_reason", "updated_at"])

        _recalculate_round_results(self.round)
        result.refresh_from_db()

        self.assertEqual(result.adjustment_score, Decimal("0.50"))
        self.assertEqual(result.adjustment_reason, "발표 기여도 반영")
        self.assertEqual(result.final_score, Decimal("5.1"))

    def test_admin_adjustment_requires_reason_when_non_zero(self):
        result = StudentResult.objects.get(
            evaluation_round=self.round,
            student=self.students[0],
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("admin_student_result_adjust", args=[result.id]),
            {"adjustment_score": "0.5", "adjustment_reason": ""},
        )
        self.assertEqual(response.status_code, 302)

        result.refresh_from_db()
        self.assertEqual(result.adjustment_score, Decimal("0"))
        self.assertEqual(result.adjustment_reason, "")
        self.assertEqual(result.final_score, Decimal("4.6"))

    def test_admin_adjustment_endpoint_recalculates_final_score(self):
        result = StudentResult.objects.get(
            evaluation_round=self.round,
            student=self.students[0],
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("admin_student_result_adjust", args=[result.id]),
            {
                "adjustment_score": "0.40",
                "adjustment_reason": "관리자 검토 반영",
            },
        )
        self.assertEqual(response.status_code, 302)

        result.refresh_from_db()
        self.assertEqual(result.adjustment_score, Decimal("0.40"))
        self.assertEqual(result.adjustment_reason, "관리자 검토 반영")
        self.assertEqual(result.base_score, Decimal("4.6"))
        self.assertEqual(result.final_score, Decimal("5.0"))

    def test_zero_adjustment_clears_reason_and_restores_base_score(self):
        result = StudentResult.objects.get(
            evaluation_round=self.round,
            student=self.students[0],
        )
        result.adjustment_score = Decimal("0.50")
        result.adjustment_reason = "임시 보정"
        result.save(update_fields=["adjustment_score", "adjustment_reason", "updated_at"])
        _recalculate_round_results(self.round)

        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin_student_result_adjust", args=[result.id]),
            {"adjustment_score": "0", "adjustment_reason": "남아있어도 제거"},
        )
        self.assertEqual(response.status_code, 302)

        result.refresh_from_db()
        self.assertEqual(result.adjustment_score, Decimal("0"))
        self.assertEqual(result.adjustment_reason, "")
        self.assertEqual(result.final_score, result.base_score)
