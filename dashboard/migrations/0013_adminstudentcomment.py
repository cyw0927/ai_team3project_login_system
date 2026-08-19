from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0012_assignment_types_and_individual_submissions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AdminStudentComment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("comment", models.TextField(max_length=2000)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="student_comments_created", to=settings.AUTH_USER_MODEL)),
                ("evaluation_round", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="admin_student_comments", to="dashboard.evaluationround")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="admin_comments", to="dashboard.student")),
            ],
            options={"ordering": ["-evaluation_round__start_at", "-updated_at"]},
        ),
        migrations.AddConstraint(
            model_name="adminstudentcomment",
            constraint=models.UniqueConstraint(fields=("evaluation_round", "student"), name="unique_admin_comment_per_round_student"),
        ),
    ]
