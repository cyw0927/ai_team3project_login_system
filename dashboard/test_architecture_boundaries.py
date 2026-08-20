from pathlib import Path

from django.test import SimpleTestCase


SERVICES_DIR = Path(__file__).resolve().parent / "services"


class ServiceLayerArchitectureTests(SimpleTestCase):
    """Keep business services independent from HTTP view modules."""

    def test_services_do_not_import_views_package(self):
        violations = []
        for path in SERVICES_DIR.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            if "from ..views" in source or "import dashboard.views" in source:
                violations.append(path.name)

        self.assertEqual(
            violations,
            [],
            f"서비스 계층이 views에 의존하면 안 됩니다: {', '.join(violations)}",
        )

    def test_core_result_service_uses_public_collaborators(self):
        source = (SERVICES_DIR / "result_service.py").read_text(encoding="utf-8")

        self.assertIn("def recalculate_round_results(", source)
        self.assertIn("from .evaluation_completion_service import", source)
        self.assertIn("from .result_support_service import", source)
        self.assertNotIn("from ..views.common import", source)
