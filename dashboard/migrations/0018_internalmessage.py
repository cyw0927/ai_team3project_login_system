from django.db import migrations, models
import django.db.models.deletion


def migrate_targeted_announcements(apps, schema_editor):
    Announcement = apps.get_model("dashboard", "Announcement")
    InternalMessage = apps.get_model("dashboard", "InternalMessage")
    for announcement in Announcement.objects.filter(target_all=False):
        for student in announcement.recipients.all():
            InternalMessage.objects.create(
                recipient_id=student.id,
                sender_id=announcement.created_by_id,
                title=announcement.title,
                body=announcement.body,
                priority=announcement.priority,
            )
        announcement.delete()


class Migration(migrations.Migration):
    dependencies = [("dashboard", "0017_announcement_targets")]
    operations = [
        migrations.CreateModel(
            name="InternalMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=160)),
                ("body", models.TextField()),
                ("priority", models.CharField(choices=[("normal", "일반"), ("important", "중요"), ("urgent", "긴급")], default="normal", max_length=20)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="internal_messages", to="dashboard.student")),
                ("sender", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="internal_messages_sent", to="auth.user")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.RunPython(migrate_targeted_announcements, migrations.RunPython.noop),
    ]
