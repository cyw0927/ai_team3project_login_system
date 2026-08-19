from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0029_hrtask_evaluation_round"),
    ]

    operations = [
        migrations.AlterField(
            model_name="studentresult",
            name="adjustment_score",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=30),
        ),
        migrations.AlterField(
            model_name="studentresult",
            name="final_score",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=30),
        ),
    ]
