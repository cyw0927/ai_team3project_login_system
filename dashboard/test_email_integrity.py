from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


class EmailIntegrityAuditTests(TestCase):
    def setUp(self):
        self.User = get_user_model()

    def test_clean_database_reports_no_duplicate_email(self):
        self.User.objects.create_user(username="alpha", email="alpha@example.com")
        output = StringIO()

        call_command("audit_email_integrity", stdout=output)

        self.assertIn("중복 이메일 없음", output.getvalue())

    def test_duplicate_email_is_case_insensitive(self):
        self.User.objects.create_user(username="alpha", email="same@example.com")
        self.User.objects.create_user(username="beta", email="SAME@example.com")
        output = StringIO()

        call_command("audit_email_integrity", stdout=output)

        self.assertIn("중복 이메일 1개 발견", output.getvalue())
        self.assertIn("same@example.com", output.getvalue())

    def test_fail_on_duplicates_raises_command_error(self):
        self.User.objects.create_user(username="alpha", email="same@example.com")
        self.User.objects.create_user(username="beta", email="same@example.com")

        with self.assertRaises(CommandError):
            call_command(
                "audit_email_integrity",
                "--fail-on-duplicates",
                stdout=StringIO(),
                stderr=StringIO(),
            )

    def test_email_username_collision_is_reported(self):
        self.User.objects.create_user(username="student@example.com", email="owner@example.com")
        self.User.objects.create_user(username="student2", email="student@example.com")
        output = StringIO()

        call_command("audit_email_integrity", stdout=output)

        self.assertIn("이메일↔다른 계정 username 충돌 1건", output.getvalue())
