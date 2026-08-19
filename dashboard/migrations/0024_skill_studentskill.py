from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0023_internalmessage_recall_cleanup"),
    ]

    operations = [
        migrations.CreateModel(
            name="Skill",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=80, unique=True)),
                ("description", models.CharField(blank=True, max_length=240)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="StudentSkill",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("score", models.PositiveSmallIntegerField(default=0, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ("note", models.CharField(blank=True, max_length=300)),
                ("skill", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="student_profiles", to="dashboard.skill")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="skill_profiles", to="dashboard.student")),
            ],
            options={"ordering": ["-score", "skill__name"]},
        ),
        migrations.AddConstraint(
            model_name="studentskill",
            constraint=models.UniqueConstraint(fields=("student", "skill"), name="unique_student_skill_profile"),
        ),
    ]
