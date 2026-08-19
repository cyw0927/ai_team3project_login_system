from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0014_student_affiliation_teammembership_role"),
    ]

    operations = [
        migrations.CreateModel(
            name="SelfProjectReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("satisfaction", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)], verbose_name="프로젝트 만족도")),
                ("contribution", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)], verbose_name="체감 기여도")),
                ("collaboration", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)], verbose_name="협업 만족도")),
                ("difficulty", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)], verbose_name="프로젝트 난이도")),
                ("learned", models.TextField(blank=True, max_length=2000, verbose_name="배운 점")),
                ("regret", models.TextField(blank=True, max_length=2000, verbose_name="아쉬운 점")),
                ("next_action", models.TextField(blank=True, max_length=2000, verbose_name="다음 프로젝트에서 바꾸고 싶은 점")),
                ("evaluation_round", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="self_project_reviews", to="dashboard.evaluationround")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="self_project_reviews", to="dashboard.student")),
            ],
            options={
                "ordering": ["-evaluation_round__start_at", "student"],
                "constraints": [models.UniqueConstraint(fields=("evaluation_round", "student"), name="unique_self_project_review_per_round_student")],
            },
        ),
    ]
