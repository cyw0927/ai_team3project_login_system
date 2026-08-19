from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0022_studentbadge"),
    ]

    operations = [
        migrations.AddField(
            model_name="internalmessage",
            name="recalled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="internalmessage",
            name="admin_deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
