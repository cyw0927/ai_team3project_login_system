from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0006_roundattendance"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TeamAssignmentSubmission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("submission_url", models.URLField(blank=True)),
                ("attachment", models.FileField(blank=True, upload_to="submissions/")),
                ("note", models.TextField(blank=True)),
                ("admin_comment", models.TextField(blank=True)),
                ("commented_at", models.DateTimeField(blank=True, null=True)),
                ("submitted_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("assignment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="team_submissions", to="dashboard.assignment")),
                ("commented_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assignment_submission_comments", to=settings.AUTH_USER_MODEL)),
                ("submitted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assignment_submissions", to="dashboard.student")),
                ("team", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assignment_submissions", to="dashboard.team")),
            ],
            options={"ordering": ["team__name"]},
        ),
        migrations.AddConstraint(
            model_name="teamassignmentsubmission",
            constraint=models.UniqueConstraint(fields=("assignment", "team"), name="unique_assignment_submission_per_team"),
        ),
    ]
