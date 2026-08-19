from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0009_round_three_stage_and_evaluation_started"),
    ]

    operations = [
        migrations.AddField(
            model_name="evaluationround",
            name="seed_weight",
            field=models.PositiveSmallIntegerField(
                default=100,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
            ),
        ),
    ]
