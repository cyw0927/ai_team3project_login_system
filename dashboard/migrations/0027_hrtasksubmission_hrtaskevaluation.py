from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0026_hrtaskstep"),
    ]

    operations = [
        migrations.CreateModel(
            name="HRTaskSubmission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("content", models.TextField(blank=True)),
                ("attachment", models.FileField(blank=True, upload_to="hr_task_submissions/")),
                ("submitted_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="hr_task_submissions", to="dashboard.student")),
                ("task", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="submission", to="dashboard.hrtask")),
            ],
        ),
        migrations.CreateModel(
            name="HRTaskEvaluation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("score", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ("comment", models.TextField(blank=True)),
                ("evaluated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("evaluated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="hr_task_evaluations", to="auth.user")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="hr_task_evaluations", to="dashboard.student")),
                ("task", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="evaluation", to="dashboard.hrtask")),
            ],
        ),
    ]
