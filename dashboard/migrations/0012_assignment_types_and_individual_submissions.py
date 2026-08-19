from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0011_evaluationround_seed_score_weights"),
    ]

    operations = [
        migrations.AlterField(
            model_name="assignment",
            name="evaluation_round",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="assignments",
                to="dashboard.evaluationround",
            ),
        ),
        migrations.AddField(
            model_name="assignment",
            name="assignment_type",
            field=models.CharField(
                choices=[("team", "조별과제"), ("individual", "개별과제")],
                default="team",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="assignment",
            constraint=models.UniqueConstraint(
                fields=("evaluation_round", "assignment_type"),
                name="unique_assignment_type_per_round",
            ),
        ),
        migrations.CreateModel(
            name="StudentAssignmentSubmission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("submission_url", models.URLField(blank=True)),
                ("attachment", models.FileField(blank=True, upload_to="student_submissions/")),
                ("note", models.TextField(blank=True)),
                ("submitted_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("assignment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="student_submissions", to="dashboard.assignment")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="individual_assignment_submissions", to="dashboard.student")),
            ],
            options={
                "ordering": ["student__user__first_name", "student__user__username"],
            },
        ),
        migrations.AddConstraint(
            model_name="studentassignmentsubmission",
            constraint=models.UniqueConstraint(
                fields=("assignment", "student"),
                name="unique_assignment_submission_per_student",
            ),
        ),
    ]
