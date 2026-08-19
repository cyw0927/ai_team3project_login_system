from django.db import migrations, models


def normalize_round_statuses(apps, schema_editor):
    EvaluationRound = apps.get_model("dashboard", "EvaluationRound")
    # 기존 4단계 데이터를 3단계로 정리한다.
    # 기존 in_progress는 이미 평가 단계였으므로 먼저 평가 시작 상태로 보존한다.
    EvaluationRound.objects.filter(status="in_progress").update(evaluation_started=True)
    # preparing = 회차는 시작됐지만 평가 전 -> 진행 중 / 평가 미시작
    EvaluationRound.objects.filter(status="preparing").update(
        status="in_progress", evaluation_started=False
    )
    # 시작 전/종료 회차는 평가 시작 플래그를 끈다.
    EvaluationRound.objects.filter(status__in=["scheduled", "ended"]).update(
        evaluation_started=False
    )


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0008_evaluationround_preparing_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="evaluationround",
            name="evaluation_started",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(normalize_round_statuses, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="evaluationround",
            name="status",
            field=models.CharField(
                choices=[
                    ("scheduled", "시작 전"),
                    ("in_progress", "진행 중"),
                    ("ended", "종료"),
                ],
                default="scheduled",
                max_length=20,
            ),
        ),
    ]
