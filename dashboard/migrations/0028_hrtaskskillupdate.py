from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0027_hrtasksubmission_hrtaskevaluation"),
    ]

    operations = [
        migrations.CreateModel(
            name="HRTaskSkillUpdate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("previous_score", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ("new_score", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ("task_score", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ("skill_weight", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(100)])),
                ("skill", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="hr_task_updates", to="dashboard.skill")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="hr_task_skill_updates", to="dashboard.student")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="skill_updates", to="dashboard.hrtask")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="hrtaskskillupdate",
            constraint=models.UniqueConstraint(fields=("task", "skill"), name="unique_hr_task_skill_update"),
        ),
    ]
