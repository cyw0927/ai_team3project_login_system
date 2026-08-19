from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0032_hrtaskstep_detail"),
    ]

    operations = [
        migrations.AddField(
            model_name="adminstudentcomment",
            name="read_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
