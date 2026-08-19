from django.db import migrations, models


def mark_existing_round_templates_as_snapshots(apps, schema_editor):
    EvaluationTemplate = apps.get_model('dashboard', 'EvaluationTemplate')
    EvaluationTemplate.objects.filter(evaluation_round__isnull=False).update(is_snapshot=True)


class Migration(migrations.Migration):
    dependencies = [
        ('dashboard', '0018_internalmessage'),
    ]

    operations = [
        migrations.AddField(
            model_name='evaluationtemplate',
            name='is_snapshot',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_existing_round_templates_as_snapshots, migrations.RunPython.noop),
    ]
