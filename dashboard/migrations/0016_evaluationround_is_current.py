from django.db import migrations, models


def choose_initial_current_round(apps, schema_editor):
    EvaluationRound = apps.get_model("dashboard", "EvaluationRound")
    selected = (
        EvaluationRound.objects.filter(status="in_progress").order_by("-start_at").first()
        or EvaluationRound.objects.filter(status="scheduled").order_by("start_at").first()
        or EvaluationRound.objects.order_by("-start_at").first()
    )
    if selected:
        EvaluationRound.objects.filter(pk=selected.pk).update(is_current=True)


class Migration(migrations.Migration):
    dependencies = [("dashboard", "0015_selfprojectreview")]
    operations = [
        migrations.AddField(
            model_name="evaluationround",
            name="is_current",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.RunPython(choose_initial_current_round, migrations.RunPython.noop),
    ]
