from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0002_result_weights_and_adjustments"),
    ]

    operations = [
        migrations.AddField(
            model_name="evaluationround",
            name="is_locked",
            field=models.BooleanField(default=False),
        ),
    ]
