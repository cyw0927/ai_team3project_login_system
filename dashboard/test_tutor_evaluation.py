from datetime import timedelta
from unittest.mock import patch

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


class TutorTeamEvaluationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="tutor_admin",
            password="TutorPass!2026",
            is_staff=True,
            is_superuser=True,
        )
        now = timezone.now()
        self.round = EvaluationRound.objects.create(
            name="튜터 평가 테스트",
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=2),
            status=EvaluationRound.Status.IN_PROGRESS,
            evaluation_started=True,
            is_locked=False,
            team_weight=40,
            personal_weight=30,
        )
        self.team = Team.objects.create(
            evaluation_round=self.round,
            name="테스트팀",
            is_active=True,
        )
        self.template = EvaluationTemplate.objects.create(
            name="팀 평가 문항",
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
            evaluation_round=self.round,
            is_active=True,
        )
        self.criterion = EvaluationCriterion.objects.create(
            template=self.template,
            title="완성도",
            order=1,
            max_score=5,
            is_required=True,
        )
        self.client.force_login(self.admin)

    def test_tutor_page_opens_and_creates_inactive_tutor_profile(self):
        response = self.client.get(reverse("admin_tutor_evaluations"), {"round": self.round.id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "튜터 평가")
        profile = Student.objects.get(user=self.admin)
        self.assertFalse(profile.is_active)
        self.assertEqual(profile.affiliation, "튜터")

    @patch("dashboard.views.admin_tutor._recalculate_round_results")
    def test_tutor_submits_one_evaluation_per_team_with_comment(self, recalc_mock):
        response = self.client.post(
            reverse("admin_tutor_evaluations"),
            {
                "round_id": self.round.id,
                "team_id": self.team.id,
                f"score_{self.criterion.id}": "4",
                "comment": "발표 구조가 명확했습니다.",
            },
        )
        self.assertEqual(response.status_code, 302)
        evaluation = TeamEvaluation.objects.get(
            evaluation_round=self.round,
            target_team=self.team,
            evaluator__user=self.admin,
        )
        self.assertTrue(evaluation.is_submitted)
        self.assertEqual(evaluation.comment, "발표 구조가 명확했습니다.")
        self.assertEqual(evaluation.scores.get(criterion=self.criterion).score, 4)
        recalc_mock.assert_called_once_with(self.round)

    def test_tutor_input_is_blocked_before_evaluation_start(self):
        self.round.evaluation_started = False
        self.round.save(update_fields=["evaluation_started", "updated_at"])
        response = self.client.post(
            reverse("admin_tutor_evaluations"),
            {
                "round_id": self.round.id,
                "team_id": self.team.id,
                f"score_{self.criterion.id}": "5",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            TeamEvaluation.objects.filter(
                evaluation_round=self.round,
                target_team=self.team,
                evaluator__user=self.admin,
            ).exists()
        )

    @patch("dashboard.views.admin_tutor._recalculate_round_results")
    def test_weight_save_accepts_40_30_30(self, recalc_mock):
        response = self.client.post(
            reverse("admin_result_weights_save"),
            {
                "round_id": self.round.id,
                "team_weight": "40",
                "personal_weight": "30",
                "tutor_weight": "30",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.round.refresh_from_db()
        self.assertEqual(self.round.team_weight, 40)
        self.assertEqual(self.round.personal_weight, 30)
        recalc_mock.assert_called_once_with(self.round)

    def test_new_round_defaults_to_40_30_30_policy(self):
        start = timezone.localtime(timezone.now() + timedelta(days=1))
        end = start + timedelta(hours=2)
        response = self.client.post(
            reverse("admin_round_create"),
            {
                "name": "새 회차",
                "start_at": start.strftime("%Y-%m-%dT%H:%M"),
                "end_at": end.strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertEqual(response.status_code, 302)
        created = EvaluationRound.objects.get(name="새 회차")
        self.assertEqual(created.team_weight, 40)
        self.assertEqual(created.personal_weight, 30)
        self.assertEqual(100 - created.team_weight - created.personal_weight, 30)


class TutorScoreAggregationTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.round = EvaluationRound.objects.create(
            name="40 30 30 집계",
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=2),
            status=EvaluationRound.Status.IN_PROGRESS,
            evaluation_started=True,
            team_weight=40,
            personal_weight=30,
        )
        self.team = Team.objects.create(evaluation_round=self.round, name="A팀")

        self.user1 = User.objects.create_user(username="s1", first_name="학생1")
        self.user2 = User.objects.create_user(username="s2", first_name="학생2")
        self.student1 = Student.objects.create(user=self.user1)
        self.student2 = Student.objects.create(user=self.user2)
        TeamMembership.objects.create(team=self.team, student=self.student1)
        TeamMembership.objects.create(team=self.team, student=self.student2)

        team_template = EvaluationTemplate.objects.create(
            name="팀",
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
            evaluation_round=self.round,
        )
        personal_template = EvaluationTemplate.objects.create(
            name="개인",
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
            evaluation_round=self.round,
        )
        self.team_criterion = EvaluationCriterion.objects.create(
            template=team_template,
            title="팀 항목",
            order=1,
            max_score=5,
        )
        self.personal_criterion = EvaluationCriterion.objects.create(
            template=personal_template,
            title="개인 항목",
            order=1,
            max_score=5,
        )

        peer_team_eval = TeamEvaluation.objects.create(
            evaluation_round=self.round,
            evaluator=self.student2,
            target_team=self.team,
            is_submitted=True,
            submitted_at=timezone.now(),
        )
        TeamEvaluationScore.objects.create(
            evaluation=peer_team_eval,
            criterion=self.team_criterion,
            score=4,
        )
        personal_eval = PersonalEvaluation.objects.create(
            evaluation_round=self.round,
            evaluator=self.student2,
            target_student=self.student1,
            is_submitted=True,
            submitted_at=timezone.now(),
        )
        PersonalEvaluationScore.objects.create(
            evaluation=personal_eval,
            criterion=self.personal_criterion,
            score=5,
        )

        tutor_user = User.objects.create_user(username="tutor", is_staff=True)
        self.tutor = Student.objects.create(user=tutor_user, is_active=False, affiliation="튜터")
        self.tutor_eval = TeamEvaluation.objects.create(
            evaluation_round=self.round,
            evaluator=self.tutor,
            target_team=self.team,
            is_submitted=True,
            submitted_at=timezone.now(),
        )
        TeamEvaluationScore.objects.create(
            evaluation=self.tutor_eval,
            criterion=self.team_criterion,
            score=3,
        )

    @patch("dashboard.services.result_service._apply_assignment_skill_impacts")
    @patch("dashboard.services.result_service._badge_rank_map", return_value={})
    @patch("dashboard.services.result_service._complete_personal_evaluator_ids")
    @patch("dashboard.services.result_service._complete_team_evaluator_ids")
    def test_final_score_uses_team40_personal30_tutor30(
        self,
        complete_team,
        complete_personal,
        badge_rank,
        skill_impacts,
    ):
        complete_team.return_value = [self.student2.id]
        complete_personal.return_value = [self.student2.id]

        _recalculate_round_results(self.round)
        result = StudentResult.objects.get(evaluation_round=self.round, student=self.student1)
        self.assertFalse(result.is_excluded)
        self.assertAlmostEqual(float(result.team_score), 4.0, places=2)
        self.assertAlmostEqual(float(result.personal_score), 5.0, places=2)
        # 4*0.40 + 5*0.30 + 3*0.30 = 4.00
        self.assertAlmostEqual(float(result.base_score), 4.0, places=2)
        self.assertAlmostEqual(float(result.final_score), 4.0, places=2)

    @patch("dashboard.services.result_service._apply_assignment_skill_impacts")
    @patch("dashboard.services.result_service._badge_rank_map", return_value={})
    @patch("dashboard.services.result_service._complete_personal_evaluator_ids")
    @patch("dashboard.services.result_service._complete_team_evaluator_ids")
    def test_student_is_excluded_until_required_tutor_team_score_exists(
        self,
        complete_team,
        complete_personal,
        badge_rank,
        skill_impacts,
    ):
        complete_team.return_value = [self.student2.id]
        complete_personal.return_value = [self.student2.id]
        self.tutor_eval.delete()

        _recalculate_round_results(self.round)
        result = StudentResult.objects.get(evaluation_round=self.round, student=self.student1)
        self.assertTrue(result.is_excluded)
        self.assertIsNone(result.rank)
