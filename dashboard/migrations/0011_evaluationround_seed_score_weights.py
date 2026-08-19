from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0010_evaluationround_seed_weight"),
    ]

    operations = [
        migrations.AddField(
            model_name="evaluationround",
            name="seed_team_weight",
            field=models.PositiveSmallIntegerField(
                default=40,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
            ),
        ),
        migrations.AddField(
            model_name="evaluationround",
            name="seed_personal_weight",
            field=models.PositiveSmallIntegerField(
                default=60,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
            ),
        ),
    ]
