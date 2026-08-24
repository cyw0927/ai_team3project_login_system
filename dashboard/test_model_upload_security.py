from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from dashboard.models import Assignment, EvaluationRound
from dashboard.upload_policy import validate_upload


class ModelUploadSecurityTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.round = EvaluationRound.objects.create(
            name="upload-security-round",
            start_at=now,
            end_at=now + timedelta(days=1),
        )

    def test_direct_model_save_rejects_disallowed_extension(self):
        attachment = SimpleUploadedFile(
            "attack.html",
            b"<script>alert(1)</script>",
            content_type="text/html",
        )
        assignment = Assignment(
            evaluation_round=self.round,
            assignment_type=Assignment.AssignmentType.TEAM,
            title="unsafe",
            attachment=attachment,
        )

        with self.assertRaises(ValidationError):
            assignment.save()

    def test_direct_model_save_rejects_script_content_type(self):
        attachment = SimpleUploadedFile(
            "payload.txt",
            b"alert(1)",
            content_type="application/javascript",
        )
        assignment = Assignment(
            evaluation_round=self.round,
            assignment_type=Assignment.AssignmentType.TEAM,
            title="unsafe-content-type",
            attachment=attachment,
        )

        with self.assertRaises(ValidationError):
            assignment.save()

    def test_shared_policy_enforces_size_limit(self):
        attachment = SimpleUploadedFile("small.pdf", b"12345", content_type="application/pdf")

        with self.assertRaises(ValidationError):
            validate_upload(attachment, max_bytes=4)
