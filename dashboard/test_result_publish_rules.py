from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from .models import (
    EvaluationRound,
    ResultPublishSetting,
    Student,
    StudentResult,
    Team,
    TeamMembership,
    TeamResult,
)
from .services.student_result_service import build_student_result_context


class StudentResultPublishRuleTests(TestCase):
    """학생 결과 공개/예약 공개 및 항목별 노출 규칙 회귀 테스트."""

    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.user = User.objects.create_user(
            username="publish_student",
            password="test1234!",
            first_name="공개학생",
        )
        cls.student = Student.objects.create(user=cls.user)

        cls.round = EvaluationRound.objects.create(
            name="결과 공개 테스트",
            start_at=now - timedelta(days=1),
            end_at=now - timedelta(hours=1),
            status=EvaluationRound.Status.ENDED,
            evaluation_started=False,
            team_weight=40,
            personal_weight=60,
        )
        cls.team = Team.objects.create(
            evaluation_round=cls.round,
            name="공개팀",
            is_active=True,
        )
        TeamMembership.objects.create(team=cls.team, student=cls.student)
        TeamResult.objects.create(
            evaluation_round=cls.round,
            team=cls.team,
            score=Decimal("4.20"),
            rank=1,
            is_excluded=False,
        )
        StudentResult.objects.create(
            evaluation_round=cls.round,
            student=cls.student,
            team_score=Decimal("4.20"),
            personal_score=Decimal("4.60"),
            base_score=Decimal("4.44"),
            final_score=Decimal("4.44"),
            rank=2,
            is_excluded=False,
        )

    def _setting(self, **overrides):
        defaults = {
            "is_published": False,
            "publish_at": None,
            "show_team_first_place": False,
            "show_all_team_ranks": False,
            "show_personal_score": False,
            "show_overall_rank": False,
            "show_comments": False,
        }
        defaults.update(overrides)
        return ResultPublishSetting.objects.create(
            evaluation_round=self.round,
            **defaults,
        )

    def test_unpublished_result_is_not_available(self):
        self._setting()

        context = build_student_result_context(self.student)

        self.assertFalse(context["result_published"])
        self.assertEqual(context["result"], {})
        self.assertEqual(context["available_result_rounds"], [])

    def test_future_scheduled_result_is_hidden_before_publish_time(self):
        now = timezone.now()
        self._setting(publish_at=now + timedelta(hours=2))

        context = build_student_result_context(self.student, now=now)

        self.assertFalse(context["result_published"])
        self.assertEqual(context["available_result_rounds"], [])

    def test_scheduled_result_becomes_visible_after_publish_time(self):
        now = timezone.now()
        self._setting(
            publish_at=now - timedelta(minutes=1),
            show_personal_score=True,
            show_overall_rank=True,
            show_all_team_ranks=True,
            show_team_first_place=True,
        )

        context = build_student_result_context(self.student, now=now)
        result = context["result"]

        self.assertTrue(context["result_published"])
        self.assertEqual(result["team_score"], Decimal("4.20"))
        self.assertEqual(result["personal_score"], Decimal("4.60"))
        self.assertEqual(result["final_score"], Decimal("4.44"))
        self.assertEqual(result["overall_rank"], 2)
        self.assertEqual(result["team_rank"], 1)
        self.assertEqual(len(result["team_rankings"]), 1)
        self.assertIsNotNone(result["first_team"])

    def test_immediate_publish_is_visible_even_with_future_publish_at(self):
        now = timezone.now()
        self._setting(
            is_published=True,
            publish_at=now + timedelta(days=1),
            show_personal_score=True,
        )

        context = build_student_result_context(self.student, now=now)

        self.assertTrue(context["result_published"])
        self.assertEqual(context["result"]["final_score"], Decimal("4.44"))

    def test_hidden_options_do_not_leak_scores_or_rankings(self):
        self._setting(is_published=True)

        context = build_student_result_context(self.student)
        result = context["result"]

        self.assertTrue(context["result_published"])
        self.assertIsNone(result["team_score"])
        self.assertIsNone(result["personal_score"])
        self.assertIsNone(result["final_score"])
        self.assertIsNone(result["overall_rank"])
        self.assertIsNone(result["team_rank"])
        self.assertEqual(result["breakdown"], [])
        self.assertEqual(result["score_history"], [])
        self.assertEqual(result["team_rankings"], [])
        self.assertIsNone(result["first_team"])

    def test_only_visible_rounds_are_listed_in_available_rounds(self):
        now = timezone.now()
        self._setting(is_published=True)

        hidden_round = EvaluationRound.objects.create(
            name="예약 전 회차",
            start_at=self.round.start_at - timedelta(days=7),
            end_at=self.round.end_at - timedelta(days=7),
            status=EvaluationRound.Status.ENDED,
            evaluation_started=False,
        )
        StudentResult.objects.create(
            evaluation_round=hidden_round,
            student=self.student,
            team_score=Decimal("3.00"),
            personal_score=Decimal("3.00"),
            base_score=Decimal("3.00"),
            final_score=Decimal("3.00"),
            rank=1,
            is_excluded=False,
        )
        ResultPublishSetting.objects.create(
            evaluation_round=hidden_round,
            is_published=False,
            publish_at=now + timedelta(days=1),
        )

        context = build_student_result_context(self.student, now=now)

        self.assertEqual(
            [item["id"] for item in context["available_result_rounds"]],
            [self.round.id],
        )
