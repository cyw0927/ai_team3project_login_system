from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
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
    TeamResult,
)
from .services.result_service import _recalculate_round_results


class CompleteEvaluatorAggregationTests(TestCase):
    """FIX62: 필수 평가를 모두 완료한 평가자만 집계에 반영한다."""

    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.round = EvaluationRound.objects.create(
            name="FIX62 테스트",
            start_at=now - timezone.timedelta(hours=1),
            end_at=now + timezone.timedelta(days=1),
            status=EvaluationRound.Status.IN_PROGRESS,
            evaluation_started=True,
            team_weight=40,
            personal_weight=60,
        )

        cls.students = {}
        for key in ["a", "b", "c", "d", "e"]:
            user = User.objects.create_user(
                username=f"fix62_{key}",
                password="test1234!",
                first_name=key.upper(),
            )
            cls.students[key] = Student.objects.create(user=user)

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
        cls.team3 = Team.objects.create(
            evaluation_round=cls.round,
            name="3팀",
            is_active=True,
        )

        TeamMembership.objects.create(team=cls.team1, student=cls.students["a"])
        TeamMembership.objects.create(team=cls.team1, student=cls.students["b"])
        TeamMembership.objects.create(team=cls.team2, student=cls.students["c"])
        TeamMembership.objects.create(team=cls.team3, student=cls.students["d"])
        TeamMembership.objects.create(team=cls.team3, student=cls.students["e"])

        cls.team_template = EvaluationTemplate.objects.create(
            name="FIX62 팀평가",
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
            name="FIX62 개인평가",
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

    def _submit_team(self, evaluator, target_team, score):
        evaluation = TeamEvaluation.objects.create(
            evaluation_round=self.round,
            evaluator=evaluator,
            target_team=target_team,
            is_submitted=True,
            submitted_at=timezone.now(),
        )
        TeamEvaluationScore.objects.create(
            evaluation=evaluation,
            criterion=self.team_criterion,
            score=score,
        )
        return evaluation

    def _submit_personal(self, evaluator, target_student, score):
        evaluation = PersonalEvaluation.objects.create(
            evaluation_round=self.round,
            evaluator=evaluator,
            target_student=target_student,
            is_submitted=True,
            submitted_at=timezone.now(),
        )
        PersonalEvaluationScore.objects.create(
            evaluation=evaluation,
            criterion=self.personal_criterion,
            score=score,
        )
        return evaluation

    def test_partial_team_evaluator_is_excluded_from_all_submitted_team_scores(self):
        # B는 2팀/3팀을 모두 평가해 완료자이고, A는 2팀만 평가해 미완료 상태다.
        self._submit_team(self.students["b"], self.team2, 3)
        self._submit_team(self.students["b"], self.team3, 3)
        self._submit_team(self.students["a"], self.team2, 5)

        _recalculate_round_results(self.round)

        result = TeamResult.objects.get(
            evaluation_round=self.round,
            team=self.team2,
        )
        # A가 준 5점은 일부만 제출했으므로 전체 집계에서 제외되어 B의 3점만 남는다.
        self.assertEqual(result.score, Decimal("3"))
        self.assertFalse(result.is_excluded)

    def test_finishing_last_team_evaluation_restores_previous_submissions(self):
        self._submit_team(self.students["b"], self.team2, 3)
        self._submit_team(self.students["b"], self.team3, 3)
        self._submit_team(self.students["a"], self.team2, 5)

        _recalculate_round_results(self.round)
        before = TeamResult.objects.get(evaluation_round=self.round, team=self.team2)
        self.assertEqual(before.score, Decimal("3"))

        # A가 마지막 필수 대상인 3팀까지 평가하면 기존 2팀의 5점도 다시 유효해진다.
        self._submit_team(self.students["a"], self.team3, 5)
        _recalculate_round_results(self.round)

        after = TeamResult.objects.get(evaluation_round=self.round, team=self.team2)
        self.assertEqual(after.score, Decimal("4"))

    def test_partial_personal_evaluator_is_excluded_from_all_submitted_personal_scores(self):
        # 3팀은 D/E 두 명이므로 개인평가 완료자는 상대 1명 평가만 하면 된다.
        # D가 E에게 준 3점은 완료 상태다.
        self._submit_personal(self.students["d"], self.students["e"], 3)

        # 1팀은 A/B 두 명이라 A가 B를 평가하면 완료가 되어버리므로,
        # 개인 FIX62 검증용으로 C를 1팀에 추가해 A의 필수 대상 수를 2명으로 만든다.
        TeamMembership.objects.filter(student=self.students["c"]).delete()
        TeamMembership.objects.create(team=self.team1, student=self.students["c"])

        # C는 A/B를 모두 평가해 완료자. A는 B만 평가해 미완료자.
        self._submit_personal(self.students["c"], self.students["a"], 3)
        self._submit_personal(self.students["c"], self.students["b"], 3)
        self._submit_personal(self.students["a"], self.students["b"], 5)

        _recalculate_round_results(self.round)

        result = StudentResult.objects.get(
            evaluation_round=self.round,
            student=self.students["b"],
        )
        # A의 5점은 미완료 평가자의 제출분이라 제외되고 C의 3점만 반영된다.
        self.assertEqual(result.personal_score, Decimal("3"))

    def test_finishing_last_personal_evaluation_restores_previous_submissions(self):
        TeamMembership.objects.filter(student=self.students["c"]).delete()
        TeamMembership.objects.create(team=self.team1, student=self.students["c"])

        self._submit_personal(self.students["c"], self.students["a"], 3)
        self._submit_personal(self.students["c"], self.students["b"], 3)
        self._submit_personal(self.students["a"], self.students["b"], 5)

        _recalculate_round_results(self.round)
        before = StudentResult.objects.get(
            evaluation_round=self.round,
            student=self.students["b"],
        )
        self.assertEqual(before.personal_score, Decimal("3"))

        # A가 남은 C까지 평가하면 B에게 이미 준 5점도 다시 집계된다.
        self._submit_personal(self.students["a"], self.students["c"], 5)
        _recalculate_round_results(self.round)

        after = StudentResult.objects.get(
            evaluation_round=self.round,
            student=self.students["b"],
        )
        self.assertEqual(after.personal_score, Decimal("4"))
