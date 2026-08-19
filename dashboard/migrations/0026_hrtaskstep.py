from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0025_hrtask_hrtaskskill"),
    ]

    operations = [
        migrations.CreateModel(
            name="HRTaskStep",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=160)),
                ("order", models.PositiveSmallIntegerField(default=1)),
                ("is_completed", models.BooleanField(default=False)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="steps", to="dashboard.hrtask")),
            ],
            options={"ordering": ["order", "id"]},
        ),
        migrations.AddConstraint(
            model_name="hrtaskstep",
            constraint=models.UniqueConstraint(fields=("task", "order"), name="unique_hr_task_step_order"),
        ),
    ]
