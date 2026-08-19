from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0005_adminactivitylog"),
    ]

    operations = [
        migrations.CreateModel(
            name="RoundAttendance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("present", "출석"), ("absent", "결석"), ("excused", "공결")], default="present", max_length=20)),
                ("note", models.CharField(blank=True, max_length=250)),
                ("evaluation_round", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attendance_records", to="dashboard.evaluationround")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="round_attendance_records", to="dashboard.student")),
            ],
            options={"ordering": ["evaluation_round", "student__user__first_name", "student__user__username"]},
        ),
        migrations.AddConstraint(
            model_name="roundattendance",
            constraint=models.UniqueConstraint(fields=("evaluation_round", "student"), name="unique_round_attendance"),
        ),
    ]
