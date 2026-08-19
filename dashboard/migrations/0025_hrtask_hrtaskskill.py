from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0024_skill_studentskill"),
    ]

    operations = [
        migrations.CreateModel(
            name="HRTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=160)),
                ("description", models.TextField(blank=True)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("due_date", models.DateField(blank=True, null=True)),
                ("status", models.CharField(choices=[("unassigned", "할당 전"), ("scheduled", "진행 예정"), ("in_progress", "진행 중"), ("review", "검토 요청"), ("completed", "완료")], default="unassigned", max_length=20)),
                ("priority", models.CharField(choices=[("low", "낮음"), ("normal", "보통"), ("high", "높음"), ("urgent", "긴급")], default="normal", max_length=20)),
                ("assignee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="hr_tasks", to="dashboard.student")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="hr_tasks_created", to="auth.user")),
            ],
            options={"ordering": ["status", "due_date", "-created_at"]},
        ),
        migrations.CreateModel(
            name="HRTaskSkill",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("weight", models.PositiveSmallIntegerField(default=100, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(100)])),
                ("skill", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="required_by_tasks", to="dashboard.skill")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="required_skills", to="dashboard.hrtask")),
            ],
            options={"ordering": ["-weight", "skill__name"]},
        ),
        migrations.AddConstraint(
            model_name="hrtaskskill",
            constraint=models.UniqueConstraint(fields=("task", "skill"), name="unique_hr_task_skill"),
        ),
    ]
