from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    TeamAssignmentSubmission,
    Assignment,
    EvaluationCriterion,
    EvaluationRound,
    EvaluationTemplate,
    PersonalEvaluation,
    PersonalEvaluationScore,
    Student,
    ResultPublishSetting,
    StudentResult,
    TeamResult,
    RoundAttendance,
    Team,
    TeamEvaluation,
    TeamEvaluationScore,
    TeamMembership,
    AdminStudentComment,
    SelfProjectReview,
    StudentAssignmentSubmission,
)
from .views import _cumulative_seed_scores_before, _recalculate_round_results


class EvaluationBusinessRuleTests(TestCase):
    """RFP BR-01~BR-08 핵심 규칙 회귀 테스트."""

    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.round = EvaluationRound.objects.create(
            name="테스트 평가",
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=1),
            status=EvaluationRound.Status.IN_PROGRESS,
            evaluation_started=True,
            team_weight=40,
            personal_weight=60,
        )

        cls.users = {}
        cls.students = {}
        for key in ["a", "b", "c", "d"]:
            user = User.objects.create_user(
                username=f"student_{key}",
                password="test1234!",
                first_name=key.upper(),
            )
            student = Student.objects.create(user=user)
            cls.users[key] = user
            cls.students[key] = student

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
            name="팀 평가",
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
            evaluation_round=cls.round,
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
        )
        cls.personal_criterion = EvaluationCriterion.objects.create(
            template=cls.personal_template,
            title="협업",
            order=1,
            max_score=5,
        )

    def login_a(self):
        self.client.force_login(self.users["a"])

    def test_br01_own_team_is_not_team_evaluation_target(self):
        self.login_a()
        response = self.client.get(
            reverse("student_team_evaluation"),
            {"team": self.team1.id},
        )
        self.assertEqual(response.status_code, 200)
        target_ids = [team.id for team in response.context["target_teams"]]
        self.assertNotIn(self.team1.id, target_ids)
        self.assertIn(self.team2.id, target_ids)
        self.assertIsNone(response.context["selected_team"])

    def test_br02_br03_br04_peer_targets_are_same_team_except_self(self):
        self.login_a()
        response = self.client.get(reverse("student_personal_evaluation"))
        self.assertEqual(response.status_code, 200)
        target_ids = [student.id for student in response.context["target_members"]]

        self.assertIn(self.students["b"].id, target_ids)      # BR-03
        self.assertNotIn(self.students["a"].id, target_ids)   # BR-04
        self.assertNotIn(self.students["c"].id, target_ids)   # BR-02
        self.assertNotIn(self.students["d"].id, target_ids)   # BR-02

    def test_br05_team_evaluation_unique_constraint(self):
        TeamEvaluation.objects.create(
            evaluation_round=self.round,
            evaluator=self.students["a"],
            target_team=self.team2,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TeamEvaluation.objects.create(
                    evaluation_round=self.round,
                    evaluator=self.students["a"],
                    target_team=self.team2,
                )

    def test_br05_personal_evaluation_unique_constraint(self):
        PersonalEvaluation.objects.create(
            evaluation_round=self.round,
            evaluator=self.students["a"],
            target_student=self.students["b"],
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PersonalEvaluation.objects.create(
                    evaluation_round=self.round,
                    evaluator=self.students["a"],
                    target_student=self.students["b"],
                )

    def test_br06_br07_br08_score_recalculation_uses_40_60(self):
        # A와 B가 2팀을 각각 4점으로 평가 -> 2팀 팀점수 4.00
        for evaluator in [self.students["a"], self.students["b"]]:
            evaluation = TeamEvaluation.objects.create(
                evaluation_round=self.round,
                evaluator=evaluator,
                target_team=self.team2,
                is_submitted=True,
                submitted_at=timezone.now(),
            )
            TeamEvaluationScore.objects.create(
                evaluation=evaluation,
                criterion=self.team_criterion,
                score=4,
            )

        # D가 C에게 개인평가 5점 -> C 개인점수 5.00
        peer = PersonalEvaluation.objects.create(
            evaluation_round=self.round,
            evaluator=self.students["d"],
            target_student=self.students["c"],
            is_submitted=True,
            submitted_at=timezone.now(),
        )
        PersonalEvaluationScore.objects.create(
            evaluation=peer,
            criterion=self.personal_criterion,
            score=5,
        )

        _recalculate_round_results(self.round)

        result = StudentResult.objects.get(
            evaluation_round=self.round,
            student=self.students["c"],
        )
        self.assertEqual(result.team_score, Decimal("4"))
        self.assertEqual(result.personal_score, Decimal("5"))
        self.assertEqual(result.base_score, Decimal("4.6"))
        self.assertEqual(result.final_score, Decimal("4.6"))


class AccessControlTests(TestCase):
    def setUp(self):
        self.student_user = User.objects.create_user(
            username="student", password="test1234!"
        )
        Student.objects.create(user=self.student_user)
        self.admin_user = User.objects.create_user(
            username="admin", password="test1234!", is_staff=True
        )

    def test_anonymous_user_is_redirected_from_student_page(self):
        response = self.client.get(reverse("student_home"))
        self.assertEqual(response.status_code, 302)

    def test_student_cannot_open_admin_page(self):
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("admin_rounds"))
        self.assertEqual(response.status_code, 302)

    def test_admin_is_redirected_from_student_page(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("student_home"))
        self.assertEqual(response.status_code, 302)


class TeamAssignmentAndPublishRuleTests(TestCase):
    """BR-09, BR-10 및 회차별 팀 소속 무결성 테스트."""

    def setUp(self):
        now = timezone.now()
        self.previous_round = EvaluationRound.objects.create(
            name="이전 평가",
            start_at=now - timedelta(days=8),
            end_at=now - timedelta(days=7),
            status=EvaluationRound.Status.ENDED,
            evaluation_started=True,
        )
        self.current_round = EvaluationRound.objects.create(
            name="현재 평가",
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=1),
            status=EvaluationRound.Status.IN_PROGRESS,
            evaluation_started=True,
        )

        self.admin = User.objects.create_user(
            username="seed_admin", password="test1234!", is_staff=True
        )
        self.students = []
        for index, score in enumerate(["5.00", "4.00", "3.00", "2.00"], start=1):
            user = User.objects.create_user(
                username=f"seed_student_{index}",
                password="test1234!",
                first_name=f"학생{index}",
            )
            student = Student.objects.create(user=user)
            self.students.append(student)
            StudentResult.objects.create(
                evaluation_round=self.previous_round,
                student=student,
                team_score=Decimal(score),
                personal_score=Decimal(score),
                base_score=Decimal(score),
                final_score=Decimal(score),
                rank=index,
                is_excluded=False,
            )

    def test_br09_auto_preview_uses_previous_final_scores(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin_auto_preview"),
            {
                "round_id": self.current_round.id,
                "team_count": "2",
                "assignment_rule": "seed",
                "avoid_previous": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        preview = self.client.session.get("team_assignment_preview")
        self.assertEqual(len(preview), 2)

        assigned_ids = [
            student_id
            for team in preview
            for student_id in team["student_ids"]
        ]
        self.assertCountEqual(
            assigned_ids,
            [student.id for student in self.students],
        )
        # 4명/2팀이면 각 팀 2명이어야 한다.
        self.assertEqual(sorted(len(team["student_ids"]) for team in preview), [2, 2])
        # 시드 점수가 실제 미리보기 정보에 전달되는지 확인한다.
        seed_scores = [
            member["seed_score"]
            for team in preview
            for member in team["members"]
        ]
        self.assertCountEqual(seed_scores, [5.0, 4.0, 3.0, 2.0])


    def test_br09_cumulative_seed_uses_average_of_all_previous_rounds(self):
        older_round = EvaluationRound.objects.create(
            name="더 이전 평가",
            start_at=self.previous_round.start_at - timedelta(days=7),
            end_at=self.previous_round.end_at - timedelta(days=7),
            status=EvaluationRound.Status.ENDED,
            evaluation_started=False,
        )
        student = self.students[0]
        StudentResult.objects.create(
            evaluation_round=older_round,
            student=student,
            team_score=Decimal("3.00"),
            personal_score=Decimal("3.00"),
            base_score=Decimal("3.00"),
            final_score=Decimal("3.00"),
            rank=1,
            is_excluded=False,
        )

        scores = _cumulative_seed_scores_before(self.current_round)
        # 기존 previous_round 5.00 + older_round 3.00 평균 = 4.00
        self.assertEqual(scores[student.id], Decimal("4.00"))

    def test_one_student_cannot_join_two_teams_in_same_round(self):
        team1 = Team.objects.create(
            evaluation_round=self.current_round, name="1팀", is_active=True
        )
        team2 = Team.objects.create(
            evaluation_round=self.current_round, name="2팀", is_active=True
        )
        TeamMembership.objects.create(team=team1, student=self.students[0])
        with self.assertRaises(ValidationError):
            TeamMembership.objects.create(team=team2, student=self.students[0])

    def test_same_student_can_join_team_in_different_round(self):
        previous_team = Team.objects.create(
            evaluation_round=self.previous_round, name="이전 1팀", is_active=True
        )
        current_team = Team.objects.create(
            evaluation_round=self.current_round, name="현재 1팀", is_active=True
        )
        TeamMembership.objects.create(team=previous_team, student=self.students[0])
        membership = TeamMembership.objects.create(
            team=current_team, student=self.students[0]
        )
        self.assertIsNotNone(membership.pk)

    def test_br10_hidden_personal_score_is_not_leaked_in_context(self):
        student = self.students[0]
        current_team = Team.objects.create(
            evaluation_round=self.current_round, name="공개테스트팀", is_active=True
        )
        TeamMembership.objects.create(team=current_team, student=student)
        team_result = TeamResult.objects.create(
            evaluation_round=self.current_round,
            team=current_team,
            score=Decimal("4.20"),
            rank=2,
            is_excluded=False,
        )
        StudentResult.objects.create(
            evaluation_round=self.current_round,
            student=student,
            team_score=Decimal("4.20"),
            personal_score=Decimal("4.80"),
            base_score=Decimal("4.56"),
            final_score=Decimal("4.56"),
            rank=3,
            is_excluded=False,
        )
        ResultPublishSetting.objects.create(
            evaluation_round=self.current_round,
            is_published=True,
            show_team_first_place=False,
            show_all_team_ranks=False,
            show_personal_score=False,
            show_overall_rank=False,
            show_comments=False,
        )

        self.client.force_login(student.user)
        response = self.client.get(reverse("student_results"))
        self.assertEqual(response.status_code, 200)
        result = response.context["result"]

        self.assertIsNone(result["team_rank"])
        self.assertIsNone(result["team_score"])
        self.assertIsNone(result["personal_score"])
        self.assertIsNone(result["final_score"])
        self.assertIsNone(result["overall_rank"])
        self.assertEqual(result["breakdown"], [])
        self.assertEqual(result["team_rankings"], [])
        self.assertIsNone(result["first_team"])

    def test_br10_enabled_items_are_returned(self):
        student = self.students[1]
        team1 = Team.objects.create(
            evaluation_round=self.current_round, name="1팀", is_active=True
        )
        team2 = Team.objects.create(
            evaluation_round=self.current_round, name="2팀", is_active=True
        )
        TeamMembership.objects.create(team=team2, student=student)
        TeamResult.objects.create(
            evaluation_round=self.current_round,
            team=team1,
            score=Decimal("4.90"),
            rank=1,
            is_excluded=False,
        )
        TeamResult.objects.create(
            evaluation_round=self.current_round,
            team=team2,
            score=Decimal("4.30"),
            rank=2,
            is_excluded=False,
        )
        StudentResult.objects.create(
            evaluation_round=self.current_round,
            student=student,
            team_score=Decimal("4.30"),
            personal_score=Decimal("4.50"),
            base_score=Decimal("4.42"),
            final_score=Decimal("4.42"),
            rank=4,
            is_excluded=False,
        )
        ResultPublishSetting.objects.create(
            evaluation_round=self.current_round,
            is_published=True,
            show_team_first_place=True,
            show_all_team_ranks=True,
            show_personal_score=True,
            show_overall_rank=True,
            show_comments=False,
        )

        self.client.force_login(student.user)
        response = self.client.get(reverse("student_results"))
        result = response.context["result"]

        self.assertEqual(result["team_rank"], 2)
        self.assertEqual(result["personal_score"], Decimal("4.50"))
        self.assertEqual(result["final_score"], Decimal("4.42"))
        self.assertEqual(result["overall_rank"], 4)
        self.assertEqual(len(result["breakdown"]), 3)
        self.assertEqual(len(result["team_rankings"]), 2)
        self.assertEqual(result["first_team"].team_id, team1.id)


@override_settings(MEDIA_ROOT="/tmp/ax_eval_test_media")
class RoundAssignmentAndDownloadTests(TestCase):
    """회차 상태, 과제 제출 가능 시점, 파일 다운로드 회귀 테스트."""

    def setUp(self):
        now = timezone.now()
        self.admin = User.objects.create_user(
            username="round_admin",
            password="test1234!",
            is_staff=True,
        )
        self.student_user = User.objects.create_user(
            username="round_student",
            password="test1234!",
            first_name="학생",
        )
        self.student = Student.objects.create(user=self.student_user)
        self.other_user = User.objects.create_user(
            username="round_other",
            password="test1234!",
            first_name="다른학생",
        )
        self.other_student = Student.objects.create(user=self.other_user)

        self.round = EvaluationRound.objects.create(
            name="회차 상태 테스트",
            start_at=now + timedelta(hours=1),
            end_at=now + timedelta(days=1),
            status=EvaluationRound.Status.SCHEDULED,
            evaluation_started=False,
            is_locked=False,
        )

    def _make_ready_for_evaluation(self):
        assignment = Assignment.objects.create(
            evaluation_round=self.round,
            title="테스트 과제",
        )
        team = Team.objects.create(
            evaluation_round=self.round,
            name="1팀",
            is_active=True,
        )
        TeamMembership.objects.create(team=team, student=self.student)
        TeamMembership.objects.create(team=team, student=self.other_student)

        team_template = EvaluationTemplate.objects.create(
            name="팀 평가 템플릿",
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
            evaluation_round=self.round,
            is_active=True,
        )
        EvaluationCriterion.objects.create(
            template=team_template,
            title="완성도",
            order=1,
            max_score=5,
        )

        personal_template = EvaluationTemplate.objects.create(
            name="개인 평가 템플릿",
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
            evaluation_round=self.round,
            is_active=True,
        )
        EvaluationCriterion.objects.create(
            template=personal_template,
            title="협업",
            order=1,
            max_score=5,
        )
        return assignment, team

    def test_round_start_opens_assignment_phase_but_not_evaluation(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin_round_action", args=[self.round.id, "start"])
        )
        self.assertEqual(response.status_code, 302)

        self.round.refresh_from_db()
        self.assertEqual(self.round.status, EvaluationRound.Status.IN_PROGRESS)
        self.assertFalse(self.round.evaluation_started)
        self.assertFalse(self.round.is_locked)

    def test_evaluation_start_requires_assignment_team_and_both_templates(self):
        self.client.force_login(self.admin)
        self.round.status = EvaluationRound.Status.IN_PROGRESS
        self.round.start_at = timezone.now() - timedelta(minutes=5)
        self.round.save()

        self.client.post(
            reverse("admin_round_action", args=[self.round.id, "evaluation_start"])
        )
        self.round.refresh_from_db()
        self.assertFalse(self.round.evaluation_started)

        self._make_ready_for_evaluation()
        self.client.post(
            reverse("admin_round_action", args=[self.round.id, "evaluation_start"])
        )
        self.round.refresh_from_db()
        self.assertTrue(self.round.evaluation_started)
        self.assertFalse(self.round.is_locked)

    def test_pause_resume_and_end_change_round_flags(self):
        self._make_ready_for_evaluation()
        self.round.status = EvaluationRound.Status.IN_PROGRESS
        self.round.evaluation_started = True
        self.round.start_at = timezone.now() - timedelta(hours=1)
        self.round.save()

        self.client.force_login(self.admin)

        self.client.post(reverse("admin_round_action", args=[self.round.id, "pause"]))
        self.round.refresh_from_db()
        self.assertTrue(self.round.is_locked)

        self.client.post(reverse("admin_round_action", args=[self.round.id, "resume"]))
        self.round.refresh_from_db()
        self.assertFalse(self.round.is_locked)

        self.client.post(reverse("admin_round_action", args=[self.round.id, "end"]))
        self.round.refresh_from_db()
        self.assertEqual(self.round.status, EvaluationRound.Status.ENDED)
        self.assertFalse(self.round.evaluation_started)
        self.assertTrue(self.round.is_locked)

    def test_student_can_submit_assignment_only_before_evaluation_starts(self):
        assignment, team = self._make_ready_for_evaluation()
        self.round.status = EvaluationRound.Status.IN_PROGRESS
        self.round.start_at = timezone.now() - timedelta(hours=1)
        self.round.evaluation_started = False
        self.round.is_locked = False
        self.round.save()

        self.client.force_login(self.student_user)
        response = self.client.post(
            reverse("student_assignment_info"),
            {"submission_url": "https://example.com/submission", "note": "제출"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            TeamAssignmentSubmission.objects.filter(
                assignment=assignment,
                team=team,
            ).exists()
        )

        self.round.evaluation_started = True
        self.round.save(update_fields=["evaluation_started"])

        response = self.client.post(
            reverse("student_assignment_info"),
            {"submission_url": "https://example.com/changed", "note": "수정"},
        )
        self.assertEqual(response.status_code, 302)
        submission = TeamAssignmentSubmission.objects.get(
            assignment=assignment,
            team=team,
        )
        self.assertEqual(submission.submission_url, "https://example.com/submission")

    def test_assignment_download_forces_attachment_disposition(self):
        self.round.status = EvaluationRound.Status.IN_PROGRESS
        self.round.start_at = timezone.now() - timedelta(hours=1)
        self.round.save()

        assignment = Assignment.objects.create(
            evaluation_round=self.round,
            title="다운로드 과제",
            attachment=SimpleUploadedFile(
                "guide.txt",
                b"assignment file",
                content_type="text/plain",
            ),
        )

        self.client.force_login(self.student_user)
        response = self.client.get(
            reverse("assignment_attachment_download", args=[assignment.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("guide.txt", response["Content-Disposition"])

    def test_submission_download_is_limited_to_same_team_or_admin(self):
        self.round.status = EvaluationRound.Status.IN_PROGRESS
        self.round.start_at = timezone.now() - timedelta(hours=1)
        self.round.save()

        assignment = Assignment.objects.create(
            evaluation_round=self.round,
            title="제출 다운로드",
        )
        team1 = Team.objects.create(
            evaluation_round=self.round, name="다운로드1팀", is_active=True
        )
        team2 = Team.objects.create(
            evaluation_round=self.round, name="다운로드2팀", is_active=True
        )
        TeamMembership.objects.create(team=team1, student=self.student)
        TeamMembership.objects.create(team=team2, student=self.other_student)
        submission = TeamAssignmentSubmission.objects.create(
            assignment=assignment,
            team=team1,
            submitted_by=self.student,
            attachment=SimpleUploadedFile(
                "student.txt",
                b"student file",
                content_type="text/plain",
            ),
        )

        self.client.force_login(self.student_user)
        response = self.client.get(
            reverse("submission_attachment_download", args=[submission.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

        self.client.force_login(self.other_user)
        response = self.client.get(
            reverse("submission_attachment_download", args=[submission.id])
        )
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("submission_attachment_download", args=[submission.id])
        )
        self.assertEqual(response.status_code, 200)


class SeedWeightRegressionTests(TestCase):
    """STEP 13: 회차별 Seed 가중치 계산 회귀 테스트."""

    def setUp(self):
        now = timezone.now()
        self.student_user = User.objects.create_user(
            username="seed_weight_student",
            password="test1234!",
            first_name="가중치학생",
        )
        self.student = Student.objects.create(user=self.student_user)

        self.older_round = EvaluationRound.objects.create(
            name="2회 전",
            start_at=now - timedelta(days=21),
            end_at=now - timedelta(days=20),
            status=EvaluationRound.Status.ENDED,
            seed_weight=60,
        )
        self.previous_round = EvaluationRound.objects.create(
            name="직전",
            start_at=now - timedelta(days=14),
            end_at=now - timedelta(days=13),
            status=EvaluationRound.Status.ENDED,
            seed_weight=80,
        )
        self.latest_round = EvaluationRound.objects.create(
            name="최근",
            start_at=now - timedelta(days=7),
            end_at=now - timedelta(days=6),
            status=EvaluationRound.Status.ENDED,
            seed_weight=100,
        )
        self.target_round = EvaluationRound.objects.create(
            name="다음 회차",
            start_at=now + timedelta(days=1),
            end_at=now + timedelta(days=2),
            status=EvaluationRound.Status.SCHEDULED,
        )

        for evaluation_round, score in [
            (self.older_round, "3.00"),
            (self.previous_round, "4.00"),
            (self.latest_round, "5.00"),
        ]:
            StudentResult.objects.create(
                evaluation_round=evaluation_round,
                student=self.student,
                team_score=Decimal(score),
                personal_score=Decimal(score),
                base_score=Decimal(score),
                final_score=Decimal(score),
                rank=1,
                is_excluded=False,
            )

    def test_seed_uses_round_weighted_average(self):
        scores = _cumulative_seed_scores_before(self.target_round)
        expected = (
            Decimal("3.00") * Decimal(60)
            + Decimal("4.00") * Decimal(80)
            + Decimal("5.00") * Decimal(100)
        ) / Decimal(240)
        self.assertEqual(scores[self.student.id], expected)

    def test_zero_weight_round_is_excluded_from_seed(self):
        self.older_round.seed_weight = 0
        self.older_round.save(update_fields=["seed_weight"])
        scores = _cumulative_seed_scores_before(self.target_round)
        expected = (
            Decimal("4.00") * Decimal(80)
            + Decimal("5.00") * Decimal(100)
        ) / Decimal(180)
        self.assertEqual(scores[self.student.id], expected)


class MissingEvaluationManagementTests(TestCase):
    """STEP 11: 미제출 평가 화면 + 결석/공결 팀평가 면제 회귀 테스트."""

    def setUp(self):
        now = timezone.now()
        self.admin = User.objects.create_user(
            username="missing_admin",
            password="test1234!",
            is_staff=True,
        )
        self.round = EvaluationRound.objects.create(
            name="미제출 관리 테스트",
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=1),
            status=EvaluationRound.Status.IN_PROGRESS,
            evaluation_started=True,
        )

        self.students = []
        for idx in range(1, 5):
            user = User.objects.create_user(
                username=f"missing_student_{idx}",
                password="test1234!",
                first_name=f"학생{idx}",
                email=f"student{idx}@example.com",
            )
            self.students.append(Student.objects.create(user=user))

        self.team1 = Team.objects.create(
            evaluation_round=self.round, name="1팀", is_active=True
        )
        self.team2 = Team.objects.create(
            evaluation_round=self.round, name="2팀", is_active=True
        )
        TeamMembership.objects.create(team=self.team1, student=self.students[0])
        TeamMembership.objects.create(team=self.team1, student=self.students[1])
        TeamMembership.objects.create(team=self.team2, student=self.students[2])
        TeamMembership.objects.create(team=self.team2, student=self.students[3])

        # 학생1은 결석: 팀평가 의무에서는 빠지고 개인평가는 유지되어야 한다.
        RoundAttendance.objects.create(
            evaluation_round=self.round,
            student=self.students[0],
            status=RoundAttendance.Status.ABSENT,
        )

    def test_missing_screen_excludes_absent_student_team_requirement(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("admin_missing_evaluations"),
            {"round": self.round.id},
        )
        self.assertEqual(response.status_code, 200)
        rows = response.context["rows"]

        absent_team_rows = [
            row for row in rows
            if row["type"] == "team"
            and row["evaluator_name"] == self.students[0].name
        ]
        absent_personal_rows = [
            row for row in rows
            if row["type"] == "personal"
            and row["evaluator_name"] == self.students[0].name
        ]

        self.assertEqual(absent_team_rows, [])
        self.assertEqual(len(absent_personal_rows), 1)

    def test_submitted_evaluation_disappears_from_missing_list(self):
        submitted = TeamEvaluation.objects.create(
            evaluation_round=self.round,
            evaluator=self.students[1],
            target_team=self.team2,
            is_submitted=True,
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("admin_missing_evaluations"),
            {"round": self.round.id, "type": "team"},
        )
        rows = response.context["rows"]

        self.assertFalse(
            any(
                row["evaluator_name"] == self.students[1].name
                and row["target_name"] == self.team2.name
                for row in rows
            )
        )


class StudentScoreHistoryTests(TestCase):
    """STEP 17: 공개 회차 성적 추이와 BR-10 공개 정책 테스트."""

    def setUp(self):
        now = timezone.now()
        self.user = User.objects.create_user(
            username="history_student",
            password="test1234!",
            first_name="히스토리학생",
        )
        self.student = Student.objects.create(user=self.user)

        self.old_round = EvaluationRound.objects.create(
            name="과거 공개 회차",
            start_at=now - timedelta(days=14),
            end_at=now - timedelta(days=13),
            status=EvaluationRound.Status.ENDED,
        )
        self.latest_round = EvaluationRound.objects.create(
            name="최근 공개 회차",
            start_at=now - timedelta(days=7),
            end_at=now - timedelta(days=6),
            status=EvaluationRound.Status.ENDED,
        )

        for round_obj, score in [(self.old_round, "3.80"), (self.latest_round, "4.40")]:
            StudentResult.objects.create(
                evaluation_round=round_obj,
                student=self.student,
                team_score=Decimal(score),
                personal_score=Decimal(score),
                base_score=Decimal(score),
                final_score=Decimal(score),
                rank=1,
                is_excluded=False,
            )

        ResultPublishSetting.objects.create(
            evaluation_round=self.old_round,
            is_published=True,
            show_personal_score=True,
            show_overall_rank=True,
        )
        ResultPublishSetting.objects.create(
            evaluation_round=self.latest_round,
            is_published=True,
            show_personal_score=True,
            show_overall_rank=True,
        )

    def test_score_history_contains_published_rounds_in_order(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("student_results"))
        self.assertEqual(response.status_code, 200)
        history = response.context["result"]["score_history"]
        self.assertEqual([row["round_name"] for row in history], ["과거 공개 회차", "최근 공개 회차"])
        self.assertEqual(history[-1]["final_score"], Decimal("4.40"))

    def test_hidden_personal_score_round_is_not_in_history(self):
        hidden_round = EvaluationRound.objects.create(
            name="비공개 점수 회차",
            start_at=timezone.now() - timedelta(days=21),
            end_at=timezone.now() - timedelta(days=20),
            status=EvaluationRound.Status.ENDED,
        )
        StudentResult.objects.create(
            evaluation_round=hidden_round,
            student=self.student,
            team_score=Decimal("5.00"),
            personal_score=Decimal("5.00"),
            base_score=Decimal("5.00"),
            final_score=Decimal("5.00"),
            rank=1,
            is_excluded=False,
        )
        ResultPublishSetting.objects.create(
            evaluation_round=hidden_round,
            is_published=True,
            show_personal_score=False,
            show_overall_rank=False,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("student_results"))
        names = [row["round_name"] for row in response.context["result"]["score_history"]]
        self.assertNotIn("비공개 점수 회차", names)


class SeedScoreRatioTests(TestCase):
    """STEP 18: 실제 성적과 팀 편성 Seed 산식을 분리해 검증."""

    def setUp(self):
        now = timezone.now()
        user = User.objects.create_user(
            username="seed_ratio_student",
            password="test1234!",
            first_name="Seed비율",
        )
        self.student = Student.objects.create(user=user)
        self.history_round = EvaluationRound.objects.create(
            name="Seed 산식 회차",
            start_at=now - timedelta(days=7),
            end_at=now - timedelta(days=6),
            status=EvaluationRound.Status.ENDED,
            seed_weight=100,
            seed_team_weight=20,
            seed_personal_weight=80,
        )
        self.target_round = EvaluationRound.objects.create(
            name="다음 회차",
            start_at=now + timedelta(days=1),
            end_at=now + timedelta(days=2),
            status=EvaluationRound.Status.SCHEDULED,
        )
        self.result = StudentResult.objects.create(
            evaluation_round=self.history_round,
            student=self.student,
            team_score=Decimal("2.00"),
            personal_score=Decimal("5.00"),
            base_score=Decimal("3.80"),
            final_score=Decimal("3.80"),
            rank=1,
            is_excluded=False,
        )

    def test_seed_20_80_uses_team_and_personal_scores_not_final_score(self):
        scores = _cumulative_seed_scores_before(self.target_round)
        # 2*20% + 5*80% = 4.4
        self.assertEqual(scores[self.student.id], Decimal("4.40"))
        # 실제 성적 값은 기존 40:60 산식의 final_score를 그대로 유지한다.
        self.result.refresh_from_db()
        self.assertEqual(self.result.final_score, Decimal("3.80"))


class DemoFlowSmokeTests(TestCase):
    """STEP 21: 관리자/학생 핵심 시연 동선이 200 응답으로 이어지는지 확인."""

    @classmethod
    def setUpTestData(cls):
        now = timezone.now()

        cls.admin = User.objects.create_user(
            username="flow_admin",
            password="test1234!",
            first_name="관리자",
            is_staff=True,
        )
        student_user = User.objects.create_user(
            username="flow_student",
            password="test1234!",
            first_name="학생",
            email="flow_student@example.com",
        )
        cls.student = Student.objects.create(user=student_user)

        cls.round = EvaluationRound.objects.create(
            name="시연 동선 테스트 회차",
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=2),
            status=EvaluationRound.Status.IN_PROGRESS,
            evaluation_started=False,
            team_weight=40,
            personal_weight=60,
            seed_weight=100,
            seed_team_weight=40,
            seed_personal_weight=60,
        )

        cls.team = Team.objects.create(
            evaluation_round=cls.round,
            name="1팀",
            project_title="시연 프로젝트",
            is_active=True,
        )
        TeamMembership.objects.create(
            team=cls.team,
            student=cls.student,
            is_leader=True,
        )

        cls.assignment = Assignment.objects.create(
            evaluation_round=cls.round,
            title="시연 과제",
            description="시연 동선 점검용 과제",
        )

        team_template = EvaluationTemplate.objects.create(
            name="시연 팀 평가",
            evaluation_type=EvaluationTemplate.EvaluationType.TEAM,
            evaluation_round=cls.round,
            is_active=True,
        )
        EvaluationCriterion.objects.create(
            template=team_template,
            title="완성도",
            description="결과물 완성도",
            order=1,
            max_score=5,
            is_required=True,
        )

        personal_template = EvaluationTemplate.objects.create(
            name="시연 개인 평가",
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
            evaluation_round=cls.round,
            is_active=True,
        )
        EvaluationCriterion.objects.create(
            template=personal_template,
            title="기여도",
            description="팀 기여도",
            order=1,
            max_score=5,
            is_required=True,
        )

        ResultPublishSetting.objects.create(
            evaluation_round=cls.round,
            is_published=False,
            show_team_first_place=True,
            show_all_team_ranks=True,
            show_personal_score=True,
            show_overall_rank=True,
            show_comments=True,
        )

    def test_admin_demo_navigation_pages_open(self):
        self.client.force_login(self.admin)

        names = [
            "admin_dashboard",
            "admin_students",
            "admin_rounds",
            "admin_assignments",
            "admin_teams",
            "admin_team_assignment",
            "admin_evaluation_templates",
            "admin_evaluation_results",
            "admin_missing_evaluations",
            "admin_team_scores",
            "admin_personal_scores",
            "admin_rankings",
            "admin_result_settings",
            "admin_seed_management",
            "admin_attendance",
            "admin_announcements",
            "admin_activity_logs",
            "admin_data_management",
        ]

        for name in names:
            with self.subTest(url_name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(
                    response.status_code,
                    200,
                    f"{name} expected 200 but got {response.status_code}",
                )

    def test_student_demo_navigation_pages_open(self):
        self.client.force_login(self.student.user)

        names = [
            "student_home",
            "student_team_info",
            "student_assignment_info",
            "student_team_evaluation",
            "student_personal_evaluation",
            "student_evaluation_status",
            "student_results",
            "student_notifications",
            "student_profile",
        ]

        for name in names:
            with self.subTest(url_name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(
                    response.status_code,
                    200,
                    f"{name} expected 200 but got {response.status_code}",
                )

    def test_student_result_page_does_not_leak_unpublished_result(self):
        StudentResult.objects.create(
            evaluation_round=self.round,
            student=self.student,
            team_score=Decimal("4.00"),
            personal_score=Decimal("4.50"),
            base_score=Decimal("4.30"),
            final_score=Decimal("4.30"),
            rank=1,
            is_excluded=False,
        )

        self.client.force_login(self.student.user)
        response = self.client.get(reverse("student_results"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertNotIn("4.30", content)

    def test_admin_round_detail_opens(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("admin_round_detail", args=[self.round.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_admin_student_detail_opens(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("admin_student_detail", args=[self.student.id])
        )
        self.assertEqual(response.status_code, 200)


class AdminStudentCommentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.admin = User.objects.create_superuser(username="admin_feedback", email="admin@example.com", password="Admin1234!")
        user = User.objects.create_user(username="feedback_student", password="Student1234!", first_name="피드백학생")
        cls.student = Student.objects.create(user=user)
        cls.round = EvaluationRound.objects.create(
            name="피드백 회차",
            start_at=now - timedelta(days=1),
            end_at=now + timedelta(days=1),
            status=EvaluationRound.Status.IN_PROGRESS,
        )

    def test_admin_can_create_and_update_one_comment_per_round(self):
        self.client.force_login(self.admin)
        url = reverse("admin_student_comment_save", args=[self.student.id])
        response = self.client.post(url, {"evaluation_round_id": self.round.id, "comment": "첫 피드백"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AdminStudentComment.objects.count(), 1)
        feedback = AdminStudentComment.objects.get()
        self.assertEqual(feedback.comment, "첫 피드백")

        self.client.post(url, {"evaluation_round_id": self.round.id, "comment": "수정 피드백"})
        self.assertEqual(AdminStudentComment.objects.count(), 1)
        feedback.refresh_from_db()
        self.assertEqual(feedback.comment, "수정 피드백")

    def test_student_cannot_use_admin_comment_endpoint(self):
        self.client.force_login(self.student.user)
        response = self.client.post(
            reverse("admin_student_comment_save", args=[self.student.id]),
            {"evaluation_round_id": self.round.id, "comment": "우회"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AdminStudentComment.objects.count(), 0)


class TeamRoleAndAffiliationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="stage03admin", email="admin03@test.com", password="pass12345")
        self.user = User.objects.create_user(username="stage03student", email="s03@test.com", password="pass12345", first_name="학생03")
        self.student = Student.objects.create(user=self.user, affiliation="AX 2기")
        now = timezone.now()
        self.round = EvaluationRound.objects.create(name="역할 테스트", start_at=now, end_at=now + timedelta(days=7))
        self.team = Team.objects.create(evaluation_round=self.round, name="1팀")
        self.membership = TeamMembership.objects.create(team=self.team, student=self.student, role="백엔드")

    def test_affiliation_and_role_are_saved(self):
        self.assertEqual(self.student.affiliation, "AX 2기")
        self.assertEqual(self.membership.role, "백엔드")

    def test_admin_can_update_member_role(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin_team_member_role_update", args=[self.membership.id]),
            {"role": "발표"},
        )
        self.assertEqual(response.status_code, 302)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, "발표")

class SelfProjectReviewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="selfreview_student", password="pass12345", first_name="회고학생")
        self.student = Student.objects.create(user=self.user)
        now = timezone.now()
        self.ended_round = EvaluationRound.objects.create(
            name="종료 프로젝트",
            start_at=now - timedelta(days=10),
            end_at=now - timedelta(days=1),
            status=EvaluationRound.Status.ENDED,
        )
        self.team = Team.objects.create(evaluation_round=self.ended_round, name="회고팀")
        TeamMembership.objects.create(team=self.team, student=self.student)

    def test_student_can_create_and_update_self_review_for_ended_round(self):
        self.client.force_login(self.user)
        url = reverse("student_self_review")
        payload = {
            "evaluation_round_id": self.ended_round.id,
            "satisfaction": 5,
            "contribution": 4,
            "collaboration": 5,
            "difficulty": 3,
            "learned": "협업을 배웠다",
            "regret": "일정 관리",
            "next_action": "더 일찍 공유하기",
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SelfProjectReview.objects.count(), 1)
        review = SelfProjectReview.objects.get()
        self.assertEqual(review.satisfaction, 5)

        payload["satisfaction"] = 4
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SelfProjectReview.objects.count(), 1)
        review.refresh_from_db()
        self.assertEqual(review.satisfaction, 4)

    def test_in_progress_round_is_not_available_for_self_review(self):
        now = timezone.now()
        active_round = EvaluationRound.objects.create(
            name="진행 프로젝트",
            start_at=now - timedelta(days=1),
            end_at=now + timedelta(days=1),
            status=EvaluationRound.Status.IN_PROGRESS,
        )
        active_team = Team.objects.create(evaluation_round=active_round, name="진행팀")
        TeamMembership.objects.create(team=active_team, student=self.student)
        self.client.force_login(self.user)
        response = self.client.post(reverse("student_self_review"), {
            "evaluation_round_id": active_round.id,
            "satisfaction": 5,
            "contribution": 5,
            "collaboration": 5,
            "difficulty": 5,
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SelfProjectReview.objects.filter(evaluation_round=active_round).exists())


class StudentResultRadarChartTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.round = EvaluationRound.objects.create(
            name="레이더 테스트",
            start_at=now - timedelta(days=3),
            end_at=now - timedelta(days=1),
            status=EvaluationRound.Status.ENDED,
        )
        self.team = Team.objects.create(evaluation_round=self.round, name="레이더팀")
        self.students = []
        for index in range(3):
            user = User.objects.create_user(
                username=f"radar_student_{index}",
                password="pass12345",
                first_name=f"레이더{index}",
            )
            student = Student.objects.create(user=user)
            TeamMembership.objects.create(team=self.team, student=student)
            self.students.append(student)

        template = EvaluationTemplate.objects.create(
            name="개인 레이더 평가",
            evaluation_type=EvaluationTemplate.EvaluationType.PERSONAL,
            evaluation_round=self.round,
        )
        self.criteria = [
            EvaluationCriterion.objects.create(template=template, title="협업", order=1, max_score=5),
            EvaluationCriterion.objects.create(template=template, title="기여도", order=2, max_score=5),
            EvaluationCriterion.objects.create(template=template, title="소통", order=3, max_score=5),
        ]

        target = self.students[0]
        for evaluator, values in ((self.students[1], [5, 4, 3]), (self.students[2], [3, 4, 5])):
            evaluation = PersonalEvaluation.objects.create(
                evaluation_round=self.round,
                evaluator=evaluator,
                target_student=target,
                is_submitted=True,
                submitted_at=now - timedelta(days=1),
            )
            for criterion, value in zip(self.criteria, values):
                PersonalEvaluationScore.objects.create(evaluation=evaluation, criterion=criterion, score=value)

        TeamResult.objects.create(evaluation_round=self.round, team=self.team, score=4, rank=1)
        StudentResult.objects.create(
            evaluation_round=self.round,
            student=target,
            team_score=4,
            personal_score=4,
            base_score=4,
            final_score=4,
            rank=1,
        )
        ResultPublishSetting.objects.create(
            evaluation_round=self.round,
            is_published=True,
            show_personal_score=True,
            show_overall_rank=True,
        )

    def test_results_context_contains_criterion_radar_data(self):
        self.client.force_login(self.students[0].user)
        response = self.client.get(reverse("student_results"))
        self.assertEqual(response.status_code, 200)
        radar = response.context["result"]["radar_chart"]
        self.assertIsNotNone(radar)
        self.assertEqual([item["label"] for item in radar["items"]], ["협업", "기여도", "소통"])
        self.assertEqual(radar["items"][0]["score"], 4.0)
        self.assertEqual(radar["items"][1]["score"], 4.0)
        self.assertEqual(radar["items"][2]["score"], 4.0)


class AdminIndividualAssignmentOverviewTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.admin = User.objects.create_superuser(
            username="overview_admin", email="admin@example.com", password="pass12345"
        )
        self.round = EvaluationRound.objects.create(
            name="개별과제 현황 테스트",
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(days=1),
            status=EvaluationRound.Status.IN_PROGRESS,
        )
        self.assignment = Assignment.objects.create(
            evaluation_round=self.round,
            assignment_type=Assignment.AssignmentType.INDIVIDUAL,
            title="개별 실습",
        )
        self.students = []
        for index in range(2):
            user = User.objects.create_user(
                username=f"overview_student_{index}",
                password="pass12345",
                first_name=f"학생{index + 1}",
            )
            self.students.append(Student.objects.create(user=user, affiliation="AX 2기"))
        StudentAssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.students[0],
            submission_url="https://example.com/submission",
            note="제출 완료",
        )

    def test_round_detail_shows_individual_submission_status(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin_round_detail", args=[self.round.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["stats"]["individual_submitted"], 1)
        self.assertEqual(response.context["stats"]["individual_missing"], 1)
        self.assertContains(response, "개별과제 제출 현황")
        self.assertContains(response, "제출 완료")
        self.assertContains(response, "미제출")
