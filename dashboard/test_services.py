from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .models import EvaluationRound, Student, StudentResult
from .services.seed_service import cumulative_seed_scores_before, previous_round_for
from .services.team_assignment_service import (
    balanced_random_assignment,
    pot_seed_assignment,
    snake_seed_assignment,
)


class SeedServiceTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.target_round = EvaluationRound.objects.create(
            name="현재 회차",
            start_at=now,
            end_at=now + timedelta(days=1),
            status=EvaluationRound.Status.SCHEDULED,
        )
        user = User.objects.create_user(username="seed_service_student")
        self.student = Student.objects.create(user=user)

    def _round(self, name, days_ago, *, seed_weight=100, team_weight=40, personal_weight=60):
        return EvaluationRound.objects.create(
            name=name,
            start_at=self.target_round.start_at - timedelta(days=days_ago),
            end_at=self.target_round.start_at - timedelta(days=days_ago - 1),
            status=EvaluationRound.Status.ENDED,
            seed_weight=seed_weight,
            seed_team_weight=team_weight,
            seed_personal_weight=personal_weight,
        )

    def _result(self, evaluation_round, team_score, personal_score, *, excluded=False):
        return StudentResult.objects.create(
            evaluation_round=evaluation_round,
            student=self.student,
            team_score=Decimal(str(team_score)),
            personal_score=Decimal(str(personal_score)),
            base_score=Decimal("0"),
            final_score=Decimal("0"),
            is_excluded=excluded,
        )

    def test_cumulative_seed_applies_round_and_score_weights(self):
        older = self._round("이전 1", 14, seed_weight=100, team_weight=40, personal_weight=60)
        newer = self._round("이전 2", 7, seed_weight=50, team_weight=50, personal_weight=50)
        self._result(older, "4.00", "5.00")
        self._result(newer, "2.00", "4.00")

        scores = cumulative_seed_scores_before(self.target_round)

        # older=4.6, newer=3.0; history weight 100:50 => 4.066666...
        self.assertAlmostEqual(float(scores[self.student.id]), 4.0666666667, places=8)

    def test_cumulative_seed_ignores_excluded_and_zero_weight_rounds(self):
        included = self._round("반영", 14, seed_weight=100)
        excluded = self._round("제외 결과", 10, seed_weight=100)
        zero_weight = self._round("가중치 0", 7, seed_weight=0)
        self._result(included, "3.00", "5.00")
        self._result(excluded, "5.00", "5.00", excluded=True)
        self._result(zero_weight, "1.00", "1.00")

        scores = cumulative_seed_scores_before(self.target_round)

        self.assertEqual(scores[self.student.id], Decimal("4.20"))

    def test_previous_round_for_returns_latest_round_with_results(self):
        older = self._round("더 이전", 14)
        newer = self._round("직전", 7)
        self._result(older, "3.00", "3.00")
        self._result(newer, "4.00", "4.00")

        self.assertEqual(previous_round_for(self.target_round), newer)
        self.assertIsNone(previous_round_for(None))


class TeamAssignmentServiceTests(SimpleTestCase):
    @staticmethod
    def _students(count):
        return [SimpleNamespace(id=index) for index in range(1, count + 1)]

    def test_snake_seed_assignment_balances_high_and_low_seeds(self):
        students = self._students(6)
        seed_scores = {student.id: Decimal(7 - student.id) for student in students}

        buckets = snake_seed_assignment(students, 3, seed_scores)

        self.assertEqual([[student.id for student in bucket] for bucket in buckets], [
            [1, 6],
            [2, 5],
            [3, 4],
        ])

    @patch("dashboard.services.team_assignment_service.random.random", return_value=0.5)
    @patch("dashboard.services.team_assignment_service.random.shuffle", side_effect=lambda values: None)
    def test_pot_assignment_balances_capacity_and_preserves_all_students(self, _shuffle, _random):
        students = self._students(9)
        seed_scores = {
            1: Decimal("5.0"),
            2: Decimal("4.8"),
            3: Decimal("4.6"),
            4: Decimal("4.4"),
            5: Decimal("4.2"),
            6: Decimal("4.0"),
            7: Decimal("3.8"),
            8: Decimal("3.6"),
        }

        buckets, grade_map, counts = pot_seed_assignment(students, 3, seed_scores)

        assigned_ids = [student.id for bucket in buckets for student in bucket]
        self.assertCountEqual(assigned_ids, [student.id for student in students])
        self.assertEqual(sorted(len(bucket) for bucket in buckets), [3, 3, 3])
        self.assertEqual(grade_map[9], "U")
        self.assertEqual(counts["U"], 1)
        self.assertEqual(sum(counts.values()), len(students))

    @patch("dashboard.services.team_assignment_service.random.random", return_value=0.5)
    @patch("dashboard.services.team_assignment_service.random.shuffle", side_effect=lambda values: None)
    def test_balanced_random_avoids_duplicate_previous_team_when_possible(self, _shuffle, _random):
        students = self._students(4)
        previous_team_map = {
            1: "old-a",
            2: "old-a",
            3: "old-b",
            4: "old-b",
        }

        buckets = balanced_random_assignment(students, 2, previous_team_map)

        self.assertEqual(sorted(len(bucket) for bucket in buckets), [2, 2])
        for bucket in buckets:
            previous_teams = [previous_team_map[student.id] for student in bucket]
            self.assertEqual(len(previous_teams), len(set(previous_teams)))
