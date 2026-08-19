from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0028_hrtaskskillupdate"),
    ]

    operations = [
        migrations.AddField(
            model_name="hrtask",
            name="evaluation_round",
            field=models.ForeignKey(
                blank=True,
                help_text="연결하면 이 과제 평가가 해당 회차의 배지 산정에 반영됩니다.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="hr_tasks",
                to="dashboard.evaluationround",
            ),
        ),
    ]
