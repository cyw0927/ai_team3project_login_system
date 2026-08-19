from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("dashboard", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="evaluationround",
            name="personal_weight",
            field=models.PositiveSmallIntegerField(default=60, validators=[MinValueValidator(0), MaxValueValidator(100)]),
        ),
        migrations.AddField(
            model_name="evaluationround",
            name="team_weight",
            field=models.PositiveSmallIntegerField(default=40, validators=[MinValueValidator(0), MaxValueValidator(100)]),
        ),
        migrations.AddField(
            model_name="studentresult",
            name="base_score",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8),
        ),
        migrations.AddField(
            model_name="studentresult",
            name="adjustment_score",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=8, validators=[MinValueValidator(-5), MaxValueValidator(5)]),
        ),
        migrations.AddField(
            model_name="studentresult",
            name="adjustment_reason",
            field=models.TextField(blank=True),
        ),
    ]
