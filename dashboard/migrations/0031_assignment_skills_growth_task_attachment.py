from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0030_expand_admin_score_adjustment"),
    ]

    operations = [
        migrations.AddField(
            model_name="hrtask",
            name="attachment",
            field=models.FileField(blank=True, upload_to="growth_tasks/"),
        ),
        migrations.CreateModel(
            name="AssignmentSkill",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("weight", models.PositiveSmallIntegerField(default=100, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(100)])),
                ("assignment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="required_skills", to="dashboard.assignment")),
                ("skill", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assignment_requirements", to="dashboard.skill")),
            ],
            options={"ordering": ["assignment_id", "-weight", "skill__name"]},
        ),
        migrations.AddConstraint(
            model_name="assignmentskill",
            constraint=models.UniqueConstraint(fields=("assignment", "skill"), name="unique_assignment_skill"),
        ),
        migrations.CreateModel(
            name="AssignmentSkillImpact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("performance_score", models.DecimalField(decimal_places=2, default=0, max_digits=6)),
                ("skill_weight", models.PositiveSmallIntegerField(default=100)),
                ("previous_score", models.SmallIntegerField(default=0)),
                ("new_score", models.SmallIntegerField(default=0)),
                ("applied_delta", models.SmallIntegerField(default=0)),
                ("assignment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="skill_impacts", to="dashboard.assignment")),
                ("skill", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assignment_impacts", to="dashboard.skill")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assignment_skill_impacts", to="dashboard.student")),
            ],
            options={"ordering": ["-updated_at", "assignment_id", "skill__name"]},
        ),
        migrations.AddConstraint(
            model_name="assignmentskillimpact",
            constraint=models.UniqueConstraint(fields=("assignment", "student", "skill"), name="unique_assignment_student_skill_impact"),
        ),
    ]
