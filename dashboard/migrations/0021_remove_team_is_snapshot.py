from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0020_alter_assignment_options_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="team",
            name="is_snapshot",
        ),
    ]
