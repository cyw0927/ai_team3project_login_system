from types import SimpleNamespace

from django.test import SimpleTestCase

from dashboard.services.team_assignment_service import (
    normalize_pot_cutoffs,
    pot_count_preview,
    pot_seed_assignment,
)


class ConfigurablePotAssignmentTests(SimpleTestCase):
    def _students(self, count):
        return [SimpleNamespace(id=index) for index in range(1, count + 1)]

    def test_default_28_student_distribution_matches_20_50_80(self):
        self.assertEqual(
            pot_count_preview(28),
            {"A": 6, "B": 8, "C": 9, "D": 5},
        )

    def test_custom_boundaries_change_actual_grade_counts(self):
        students = self._students(28)
        seed_scores = {student.id: 100 - student.id for student in students}

        buckets, grade_map, counts = pot_seed_assignment(
            students,
            team_count=4,
            seed_scores=seed_scores,
            pot_cutoffs=(25, 40, 75),
        )

        self.assertEqual(counts, {"A": 7, "B": 5, "C": 9, "D": 7, "U": 0})
        self.assertEqual(sum(len(bucket) for bucket in buckets), 28)
        self.assertEqual(sum(grade == "A" for grade in grade_map.values()), 7)
        self.assertEqual(sum(grade == "D" for grade in grade_map.values()), 7)

    def test_invalid_boundaries_are_rejected(self):
        with self.assertRaises(ValueError):
            normalize_pot_cutoffs((20, 20, 80))
        with self.assertRaises(ValueError):
            normalize_pot_cutoffs((0, 50, 80))
        with self.assertRaises(ValueError):
            normalize_pot_cutoffs((20, 80, 100))
