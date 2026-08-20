from django.test import SimpleTestCase

from dashboard import views
from dashboard.services.result_service import _recalculate_round_results
from dashboard.services.seed_service import cumulative_seed_scores_before
from dashboard.views.admin_home import admin_dashboard as thin_admin_dashboard
from dashboard.views.admin_missing import admin_missing_evaluations as thin_admin_missing_evaluations
from dashboard.views.admin_results import admin_evaluation_results as thin_admin_evaluation_results
from dashboard.views.admin_seed import admin_seed_management as thin_admin_seed_management
from dashboard.views.student_results import student_results as thin_student_results


class ViewArchitectureContractTests(SimpleTestCase):
    """리팩터링 후 공개 진입점이 다시 거대 legacy View로 돌아가지 않도록 고정한다."""

    def test_public_views_use_thin_dedicated_implementations(self):
        self.assertIs(views.student_results, thin_student_results)
        self.assertIs(views.admin_dashboard, thin_admin_dashboard)
        self.assertIs(views.admin_seed_management, thin_admin_seed_management)
        self.assertIs(views.admin_evaluation_results, thin_admin_evaluation_results)
        self.assertIs(views.admin_missing_evaluations, thin_admin_missing_evaluations)

    def test_public_result_helper_uses_service_implementation(self):
        self.assertIs(views._recalculate_round_results, _recalculate_round_results)

    def test_public_seed_helper_uses_service_implementation(self):
        self.assertIs(
            views._cumulative_seed_scores_before,
            cumulative_seed_scores_before,
        )
