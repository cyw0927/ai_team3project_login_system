from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0031_assignment_skills_growth_task_attachment"),
    ]

    operations = [
        migrations.AddField(
            model_name="hrtaskstep",
            name="detail",
            field=models.TextField(blank=True),
        ),
    ]
