from pathlib import Path

from django.test import SimpleTestCase
from django.urls.resolvers import URLPattern, URLResolver

from dashboard import urls, views


REMOVED_LEGACY_VIEW_MODULES = (
    "student.py",
    "student_assignment_compat.py",
    "admin_students.py",
    "admin_teams.py",
    "admin_dashboard.py",
)


class ViewRoutingSmokeTests(SimpleTestCase):
    def test_all_url_callbacks_are_callable(self):
        def walk(patterns):
            for pattern in patterns:
                if isinstance(pattern, URLPattern):
                    yield pattern
                elif isinstance(pattern, URLResolver):
                    yield from walk(pattern.url_patterns)

        broken = []
        for pattern in walk(urls.urlpatterns):
            try:
                callback = pattern.callback
            except Exception as exc:  # pragma: no cover - reports import/resolution failures
                broken.append(f"{pattern.name or pattern.pattern}: {exc}")
                continue
            if not callable(callback):
                broken.append(pattern.name or str(pattern.pattern))

        self.assertEqual(broken, [], f"URL callback 오류: {broken}")

    def test_key_split_views_are_exported(self):
        required = (
            "student_home",
            "student_assignment_info",
            "student_team_evaluation",
            "student_personal_evaluation",
            "student_results",
            "admin_dashboard",
            "admin_operations",
            "admin_students",
            "admin_team_assignment",
            "admin_teams",
            "admin_assignments",
            "admin_round_action",
            "admin_evaluation_results",
            "admin_tutor_evaluations",
        )
        missing = [name for name in required if not callable(getattr(views, name, None))]
        self.assertEqual(missing, [], f"views export 누락: {missing}")

    def test_removed_legacy_view_files_stay_removed(self):
        views_dir = Path(__file__).resolve().parent / "views"
        present = [name for name in REMOVED_LEGACY_VIEW_MODULES if (views_dir / name).exists()]
        self.assertEqual(present, [], f"legacy view 파일이 다시 생겼습니다: {present}")
