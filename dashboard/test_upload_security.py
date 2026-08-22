from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase

from dashboard.middleware import (
    DEFAULT_UPLOAD_MAX_BYTES,
    _validate_uploaded_files,
)


class UploadSecurityTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request_with_file(self, filename, content=b"safe", content_type="application/octet-stream", path="/student/assignment/"):
        uploaded = SimpleUploadedFile(filename, content, content_type=content_type)
        return self.factory.post(path, {"attachment": uploaded})

    def test_allows_common_project_attachment(self):
        request = self._request_with_file("report.pdf", b"%PDF-test", "application/pdf")
        self.assertIsNone(_validate_uploaded_files(request))

    def test_blocks_html_attachment(self):
        request = self._request_with_file("payload.html", b"<script>alert(1)</script>", "text/html")
        error = _validate_uploaded_files(request)
        self.assertIsNotNone(error)
        self.assertIn("허용되지 않은", error)

    def test_blocks_script_content_type_even_with_allowed_extension(self):
        request = self._request_with_file("notes.txt", b"alert(1)", "application/javascript")
        error = _validate_uploaded_files(request)
        self.assertIsNotNone(error)
        self.assertIn("브라우저에서 실행", error)

    def test_blocks_oversized_general_attachment(self):
        request = self._request_with_file("large.zip", b"x", "application/zip")
        uploaded = request.FILES["attachment"]
        uploaded.size = DEFAULT_UPLOAD_MAX_BYTES + 1
        error = _validate_uploaded_files(request)
        self.assertIsNotNone(error)
        self.assertIn("20MB", error)
