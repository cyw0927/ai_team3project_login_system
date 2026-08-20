from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from .models import (
    EvaluationCriterion,
    EvaluationRound,
    EvaluationTemplate,
    PersonalEvaluation,
    Student,
    Team,
    TeamEvaluation,
    TeamMembership,
)


class PauseResumeEvaluationTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.admin = User.objects.create_user(
            username="pause_admin",
            password="test1234!",
            is_staff=True,
        )
        self.user_a = User.objects.create_user(
            username="pause_a",
            password="test1234!",
            first_name="A",
        )
        self.user_b = User.objects.create_user(
            username="pause_b",
            password="test1234!",
            first_name="B",
        )
        self.user_c = User.objects.create_user(
            username="pause_c",
            password="test1234!",
            first_name="C",
        )
        self.student_a = Student.objects.create(user=self.user_a)
        self.student_b = Student.objects.create(user=self.user_b)
        self.student_c = Student.objects.create(user=self.user_c)

        self.round = EvaluationRound.objects.create(
            name="중단 재개 테스트",
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=1),
            status=EvaluationRound.Status.IN_PROGRESS,
            evaluation_started=True,
            is_locked=False,
        )
        self.team1 = Team.objects.create(
            evaluation_round=self.round,
            name="1팀",
            is_active=True,
        )
        self.team2 = Team.objects.create(
            evaluation_round=self.round,
            name="2팀",
            is_active=True,
        )
        TeamMembership.objects.create(team=self.team1, student=self.student_a)
        TeamMembership.objects.create(team=self.team1, student=self.student_b)
        TeamMembership.objects.create(team=self.team2, student=self.student_c)

        team_template = EvaluationTemplate.objects.create(
            name="중단 테스트 팀평가",
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
            evaluation_round=self.round,
            is_active=True,
        )
        self.team_criterion = EvaluationCriterion.objects.create(
            template=team_template,
            title="완성도",
            order=1,
            max_score=5,
            is_required=True,
        )

        personal_template = EvaluationTemplate.objects.create(
            name="중단 테스트 개인평가",
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
            evaluation_round=self.round,
            is_active=True,
        )
        self.personal_criterion = EvaluationCriterion.objects.create(
            template=personal_template,
            title="협업",
            order=1,
            max_score=5,
            is_required=True,
        )

    def _pause(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin_round_action", args=[self.round.id, "pause"])
        )
        self.assertEqual(response.status_code, 302)
        self.round.refresh_from_db()
        self.assertTrue(self.round.is_locked)

    def _resume(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin_round_action", args=[self.round.id, "resume"])
        )
        self.assertEqual(response.status_code, 302)
        self.round.refresh_from_db()
        self.assertFalse(self.round.is_locked)

    def test_paused_team_evaluation_post_does_not_create_evaluation(self):
        self._pause()
        self.client.force_login(self.user_a)

        response = self.client.post(
            reverse("student_team_evaluation"),
            {
                "target_team_id": str(self.team2.id),
                f"criterion_{self.team_criterion.id}": "5",
                "comment": "중단 중 제출 시도",
                "action": "submit",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            TeamEvaluation.objects.filter(
                evaluation_round=self.round,
                evaluator=self.student_a,
                target_team=self.team2,
            ).exists()
        )
        self.assertFalse(response.context["evaluation_open"])
        self.assertTrue(response.context["evaluation_locked"])

    def test_resume_allows_team_evaluation_submission_again(self):
        self._pause()
        self._resume()
        self.client.force_login(self.user_a)

        response = self.client.post(
            reverse("student_team_evaluation"),
            {
                "target_team_id": str(self.team2.id),
                f"criterion_{self.team_criterion.id}": "5",
                "comment": "재개 후 제출",
                "action": "submit",
            },
        )

        self.assertEqual(response.status_code, 302)
        evaluation = TeamEvaluation.objects.get(
            evaluation_round=self.round,
            evaluator=self.student_a,
            target_team=self.team2,
        )
        self.assertTrue(evaluation.is_submitted)
        self.assertEqual(evaluation.comment, "재개 후 제출")

    def test_paused_personal_evaluation_post_does_not_create_evaluation(self):
        # 개인평가 선행조건(다른 팀 팀평가 완료)을 충족시킨 뒤 중단 상태만 검증한다.
        TeamEvaluation.objects.create(
            evaluation_round=self.round,
            evaluator=self.student_a,
            target_team=self.team2,
            is_submitted=True,
            submitted_at=timezone.now(),
        )
        self._pause()
        self.client.force_login(self.user_a)

        response = self.client.post(
            reverse("student_personal_evaluation"),
            {
                "target_student_id": str(self.student_b.id),
                f"criterion_{self.personal_criterion.id}": "4",
                "comment": "중단 중 개인평가",
                "action": "submit",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            PersonalEvaluation.objects.filter(
                evaluation_round=self.round,
                evaluator=self.student_a,
                target_student=self.student_b,
            ).exists()
        )
        self.assertFalse(response.context["evaluation_open"])
        self.assertTrue(response.context["evaluation_locked"])

    def test_resume_allows_personal_evaluation_submission_again(self):
        TeamEvaluation.objects.create(
            evaluation_round=self.round,
            evaluator=self.student_a,
            target_team=self.team2,
            is_submitted=True,
            submitted_at=timezone.now(),
        )
        self._pause()
        self._resume()
        self.client.force_login(self.user_a)

        response = self.client.post(
            reverse("student_personal_evaluation"),
            {
                "target_student_id": str(self.student_b.id),
                f"criterion_{self.personal_criterion.id}": "4",
                "comment": "재개 후 개인평가",
                "action": "submit",
            },
        )

        self.assertEqual(response.status_code, 302)
        evaluation = PersonalEvaluation.objects.get(
            evaluation_round=self.round,
            evaluator=self.student_a,
            target_student=self.student_b,
        )
        self.assertTrue(evaluation.is_submitted)
        self.assertEqual(evaluation.comment, "재개 후 개인평가")
