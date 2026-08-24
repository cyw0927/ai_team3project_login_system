from django.test import RequestFactory, SimpleTestCase, override_settings

from dashboard.middleware import _client_ip as audit_client_ip
from dashboard.views.auth import _client_ip as login_client_ip


class LoginClientIpSecurityTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(LOGIN_TRUST_X_FORWARDED_FOR=False)
    def test_forwarded_for_is_ignored_by_default(self):
        request = self.factory.get(
            "/login/",
            HTTP_X_FORWARDED_FOR="203.0.113.10",
            REMOTE_ADDR="10.0.0.5",
        )
        self.assertEqual(login_client_ip(request), "10.0.0.5")

    @override_settings(LOGIN_TRUST_X_FORWARDED_FOR=True)
    def test_forwarded_for_is_used_only_when_explicitly_trusted(self):
        request = self.factory.get(
            "/login/",
            HTTP_X_FORWARDED_FOR="203.0.113.10, 10.0.0.2",
            REMOTE_ADDR="10.0.0.5",
        )
        self.assertEqual(login_client_ip(request), "203.0.113.10")

    @override_settings(LOGIN_TRUST_X_FORWARDED_FOR=True)
    def test_empty_forwarded_for_falls_back_to_remote_addr(self):
        request = self.factory.get(
            "/login/",
            HTTP_X_FORWARDED_FOR="",
            REMOTE_ADDR="10.0.0.5",
        )
        self.assertEqual(login_client_ip(request), "10.0.0.5")


class AuditLogClientIpSecurityTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(LOGIN_TRUST_X_FORWARDED_FOR=False)
    def test_audit_log_ignores_forwarded_for_by_default(self):
        request = self.factory.post(
            "/management/test/",
            HTTP_X_FORWARDED_FOR="203.0.113.20",
            REMOTE_ADDR="10.0.0.8",
        )
        self.assertEqual(audit_client_ip(request), "10.0.0.8")

    @override_settings(LOGIN_TRUST_X_FORWARDED_FOR=True)
    def test_audit_log_uses_forwarded_for_only_when_trusted(self):
        request = self.factory.post(
            "/management/test/",
            HTTP_X_FORWARDED_FOR="203.0.113.20, 10.0.0.2",
            REMOTE_ADDR="10.0.0.8",
        )
        self.assertEqual(audit_client_ip(request), "203.0.113.20")
