from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0016_evaluationround_is_current"),
    ]

    operations = [
        migrations.AddField(
            model_name="announcement",
            name="target_all",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="announcement",
            name="recipients",
            field=models.ManyToManyField(
                blank=True,
                related_name="targeted_announcements",
                to="dashboard.student",
            ),
        ),
    ]
