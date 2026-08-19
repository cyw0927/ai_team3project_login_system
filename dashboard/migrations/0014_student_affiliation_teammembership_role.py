from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0013_adminstudentcomment"),
    ]

    operations = [
        migrations.RenameField(
            model_name="student",
            old_name="major",
            new_name="affiliation",
        ),
        migrations.AddField(
            model_name="teammembership",
            name="role",
            field=models.CharField(blank=True, max_length=100, verbose_name="담당 역할"),
        ),
    ]
