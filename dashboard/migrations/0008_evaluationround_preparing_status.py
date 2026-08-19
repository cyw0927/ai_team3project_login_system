from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0007_teamassignmentsubmission"),
    ]

    operations = [
        migrations.AlterField(
            model_name="evaluationround",
            name="status",
            field=models.CharField(
                choices=[
                    ("scheduled", "예정"),
                    ("preparing", "과제 진행"),
                    ("in_progress", "평가 진행"),
                    ("ended", "종료"),
                ],
                default="scheduled",
                max_length=20,
            ),
        ),
    ]
