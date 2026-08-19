from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0021_remove_team_is_snapshot"),
    ]

    operations = [
        migrations.CreateModel(
            name="StudentBadge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("badge_type", models.CharField(choices=[("mvp", "MVP"), ("growth", "성장왕"), ("consistent", "연속 우수")], max_length=20)),
                ("awarded_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("evaluation_round", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="student_badges", to="dashboard.evaluationround")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="badges", to="dashboard.student")),
            ],
            options={"ordering": ["-awarded_at", "badge_type"]},
        ),
        migrations.AddConstraint(
            model_name="studentbadge",
            constraint=models.UniqueConstraint(fields=("student", "evaluation_round", "badge_type"), name="unique_student_round_badge"),
        ),
    ]
