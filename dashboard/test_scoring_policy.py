from types import SimpleNamespace

from django.test import SimpleTestCase

from dashboard.services.scoring_policy import (
    DEFAULT_PERSONAL_WEIGHT,
    DEFAULT_TEAM_WEIGHT,
    DEFAULT_TUTOR_WEIGHT,
    tutor_weight_for,
    validate_score_weights,
)


class ScoringPolicyTests(SimpleTestCase):
    def test_default_policy_is_40_30_30(self):
        self.assertEqual(DEFAULT_TEAM_WEIGHT, 40)
        self.assertEqual(DEFAULT_PERSONAL_WEIGHT, 30)
        self.assertEqual(DEFAULT_TUTOR_WEIGHT, 30)

    def test_tutor_weight_is_remainder(self):
        round_obj = SimpleNamespace(team_weight=40, personal_weight=30)
        self.assertEqual(tutor_weight_for(round_obj), 30)

    def test_legacy_40_60_round_has_zero_tutor_weight(self):
        round_obj = SimpleNamespace(team_weight=40, personal_weight=60)
        self.assertEqual(tutor_weight_for(round_obj), 0)

    def test_validate_score_weights_requires_total_100(self):
        values, error = validate_score_weights(40, 30, 30)
        self.assertIsNone(error)
        self.assertEqual(values["tutor_weight"], 30)

        values, error = validate_score_weights(40, 40, 30)
        self.assertIsNone(values)
        self.assertIn("100%", error)
