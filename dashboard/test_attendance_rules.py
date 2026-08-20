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
    RoundAttendance,
    Student,
    Team,
    TeamEvaluation,
    TeamMembership,
)


class AttendanceEvaluationRuleTests(TestCase):
    """결석/공결자는 팀평가를 면제하고 개인평가는 허용한다."""

    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.round = EvaluationRound.objects.create(
            name="출석 규칙 테스트",
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=1),
            status=EvaluationRound.Status.IN_PROGRESS,
            evaluation_started=True,
            is_locked=False,
        )

        cls.students = {}
        for key in ["a", "b", "c", "d"]:
            user = User.objects.create_user(
                username=f"attendance_{key}",
                password="test1234!",
                first_name=key.upper(),
            )
            cls.students[key] = Student.objects.create(user=user)

        cls.team1 = Team.objects.create(
            evaluation_round=cls.round, name="1팀", is_active=True
        )
        cls.team2 = Team.objects.create(
            evaluation_round=cls.round, name="2팀", is_active=True
        )
        TeamMembership.objects.create(team=cls.team1, student=cls.students["a"])
        TeamMembership.objects.create(team=cls.team1, student=cls.students["b"])
        TeamMembership.objects.create(team=cls.team2, student=cls.students["c"])
        TeamMembership.objects.create(team=cls.team2, student=cls.students["d"])

        cls.team_template = EvaluationTemplate.objects.create(
            name="출석 팀평가",
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
            name="출석 개인평가",
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

    def setUp(self):
        self.client.force_login(self.students["a"].user)

    def _set_attendance(self, status):
        RoundAttendance.objects.update_or_create(
            evaluation_round=self.round,
            student=self.students["a"],
            defaults={"status": status},
        )

    def _team_payload(self):
        return {
            "target_team_id": str(self.team2.id),
            f"criterion_{self.team_criterion.id}": "5",
            "comment": "팀평가",
            "action": "submit",
        }

    def _personal_payload(self):
        return {
            "target_student_id": str(self.students["b"].id),
            f"criterion_{self.personal_criterion.id}": "5",
            "comment": "개인평가",
            "action": "submit",
        }

    def test_absent_student_cannot_submit_team_evaluation(self):
        self._set_attendance(RoundAttendance.Status.ABSENT)

        response = self.client.post(reverse("student_team_evaluation"), self._team_payload())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["attendance_blocked"])
        self.assertFalse(
            TeamEvaluation.objects.filter(
                evaluation_round=self.round,
                evaluator=self.students["a"],
            ).exists()
        )

    def test_absent_or_excused_student_can_submit_personal_evaluation_without_team_evaluation(self):
        for status in (RoundAttendance.Status.ABSENT, RoundAttendance.Status.EXCUSED):
            with self.subTest(status=status):
                PersonalEvaluation.objects.filter(
                    evaluation_round=self.round,
                    evaluator=self.students["a"],
                ).delete()
                self._set_attendance(status)

                response = self.client.post(
                    reverse("student_personal_evaluation"),
                    self._personal_payload(),
                )

                self.assertEqual(response.status_code, 302)
                evaluation = PersonalEvaluation.objects.get(
                    evaluation_round=self.round,
                    evaluator=self.students["a"],
                    target_student=self.students["b"],
                )
                self.assertTrue(evaluation.is_submitted)

    def test_present_student_must_finish_team_evaluation_before_personal_evaluation(self):
        self._set_attendance(RoundAttendance.Status.PRESENT)

        blocked = self.client.post(
            reverse("student_personal_evaluation"),
            self._personal_payload(),
        )
        self.assertEqual(blocked.status_code, 200)
        self.assertFalse(
            PersonalEvaluation.objects.filter(
                evaluation_round=self.round,
                evaluator=self.students["a"],
            ).exists()
        )

        team_response = self.client.post(
            reverse("student_team_evaluation"),
            self._team_payload(),
        )
        self.assertEqual(team_response.status_code, 302)
        self.assertTrue(
            TeamEvaluation.objects.filter(
                evaluation_round=self.round,
                evaluator=self.students["a"],
                target_team=self.team2,
                is_submitted=True,
            ).exists()
        )

        allowed = self.client.post(
            reverse("student_personal_evaluation"),
            self._personal_payload(),
        )
        self.assertEqual(allowed.status_code, 302)
        self.assertTrue(
            PersonalEvaluation.objects.filter(
                evaluation_round=self.round,
                evaluator=self.students["a"],
                target_student=self.students["b"],
                is_submitted=True,
            ).exists()
        )
