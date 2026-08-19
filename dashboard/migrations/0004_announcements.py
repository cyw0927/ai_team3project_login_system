from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("dashboard", "0003_evaluationround_is_locked"),
    ]

    operations = [
        migrations.CreateModel(
            name="Announcement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=160)),
                ("body", models.TextField()),
                ("priority", models.CharField(choices=[("normal", "일반"), ("important", "중요"), ("urgent", "긴급")], default="normal", max_length=20)),
                ("is_published", models.BooleanField(default=True)),
                ("publish_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="announcements_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-publish_at", "-id"]},
        ),
        migrations.CreateModel(
            name="AnnouncementRead",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("announcement", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reads", to="dashboard.announcement")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="announcement_reads", to="dashboard.student")),
            ],
        ),
        migrations.AddConstraint(
            model_name="announcementread",
            constraint=models.UniqueConstraint(fields=("announcement", "student"), name="unique_announcement_read"),
        ),
    ]
