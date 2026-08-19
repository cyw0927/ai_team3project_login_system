from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Student(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    is_active = models.BooleanField(default=True)
    affiliation = models.CharField(max_length=100, blank=True, verbose_name="소속")

    class Meta:
        ordering = ["user__first_name", "user__username"]

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    @property
    def name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def email(self):
        return self.user.email


class Skill(TimeStampedModel):
    """업무/과제 추천에 사용하는 공통 역량 사전."""

    name = models.CharField(max_length=80, unique=True)
    description = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class StudentSkill(TimeStampedModel):
    """수강생별 현재 역량 프로필. 0~100 점수로 관리한다."""

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="skill_profiles",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="student_profiles",
    )
    score = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-score", "skill__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "skill"],
                name="unique_student_skill_profile",
            )
        ]

    def __str__(self):
        return f"{self.student} / {self.skill}: {self.score}"


class EvaluationRound(TimeStampedModel):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "시작 전"
        IN_PROGRESS = "in_progress", "진행 중"
        ENDED = "ended", "종료"

    name = models.CharField(max_length=120)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    is_reopened = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    evaluation_started = models.BooleanField(default=False)
    is_current = models.BooleanField(default=False, db_index=True)
    personal_weight = models.PositiveSmallIntegerField(default=60, validators=[MinValueValidator(0), MaxValueValidator(100)])
    team_weight = models.PositiveSmallIntegerField(default=40, validators=[MinValueValidator(0), MaxValueValidator(100)])
    # 다음 회차 자동 팀 편성용 누적 Seed에서 이 회차 결과가 차지하는 가중치.
    # 예: 최근 100 / 직전 80 / 2회 전 60
    seed_weight = models.PositiveSmallIntegerField(default=100, validators=[MinValueValidator(0), MaxValueValidator(100)])
    # 실제 성적 산식(기본 팀40/개인60)과 별개인 자동 팀 편성 Seed 전용 비율.
    seed_team_weight = models.PositiveSmallIntegerField(default=40, validators=[MinValueValidator(0), MaxValueValidator(100)])
    seed_personal_weight = models.PositiveSmallIntegerField(default=60, validators=[MinValueValidator(0), MaxValueValidator(100)])

    class Meta:
        ordering = ["-start_at"]

    def __str__(self):
        return self.name


class Assignment(TimeStampedModel):
    class AssignmentType(models.TextChoices):
        TEAM = "team", "조별과제"
        INDIVIDUAL = "individual", "개별과제"

    evaluation_round = models.ForeignKey(
        EvaluationRound,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    assignment_type = models.CharField(
        max_length=20,
        choices=AssignmentType.choices,
        default=AssignmentType.TEAM,
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    attachment = models.FileField(upload_to="assignments/", blank=True)

    class Meta:
        ordering = ["evaluation_round", "assignment_type", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation_round", "assignment_type"],
                name="unique_assignment_type_per_round",
            )
        ]

    def __str__(self):
        return f"{self.get_assignment_type_display()} - {self.title}"


class AssignmentSkill(TimeStampedModel):
    """기본 회차 과제가 어떤 역량을 얼마나 반영하는지 정의한다."""

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="required_skills",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="assignment_requirements",
    )
    weight = models.PositiveSmallIntegerField(
        default=100,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
    )

    class Meta:
        ordering = ["assignment_id", "-weight", "skill__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "skill"],
                name="unique_assignment_skill",
            )
        ]

    def __str__(self):
        return f"{self.assignment} / {self.skill} {self.weight}%"


class Team(TimeStampedModel):
    evaluation_round = models.ForeignKey(
        EvaluationRound,
        on_delete=models.CASCADE,
        related_name="teams",
    )
    name = models.CharField(max_length=80)
    project_title = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["evaluation_round", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation_round", "name"],
                name="unique_team_name_per_round",
            )
        ]

    def __str__(self):
        return f"{self.evaluation_round.name} - {self.name}"


class TeamMembership(TimeStampedModel):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="memberships")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="team_memberships")
    is_leader = models.BooleanField(default=False)
    role = models.CharField(max_length=100, blank=True, verbose_name="담당 역할")

    class Meta:
        ordering = ["team", "student"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "student"],
                name="unique_student_membership_per_team",
            )
        ]

    def clean(self):
        """한 학생은 동일 평가 회차에서 하나의 팀에만 소속될 수 있다."""
        super().clean()
        if not self.team_id or not self.student_id:
            return

        duplicated = TeamMembership.objects.filter(
            student_id=self.student_id,
            team__evaluation_round_id=self.team.evaluation_round_id,
        ).exclude(pk=self.pk)
        if duplicated.exists():
            raise ValidationError(
                {"student": "한 학생은 동일 평가 회차에서 하나의 팀에만 소속될 수 있습니다."}
            )

    def save(self, *args, **kwargs):
        # ModelForm뿐 아니라 objects.create() 같은 서버 코드에서도 회차 중복 소속을 차단한다.
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.team} / {self.student}"




class TeamAssignmentSubmission(TimeStampedModel):
    """회차 과제에 대한 팀 단위 제출물과 관리자 피드백."""

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="team_submissions",
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="assignment_submissions",
    )
    submitted_by = models.ForeignKey(
        Student,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignment_submissions",
    )
    submission_url = models.URLField(blank=True)
    attachment = models.FileField(upload_to="submissions/", blank=True)
    note = models.TextField(blank=True)
    admin_comment = models.TextField(blank=True)
    commented_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignment_submission_comments",
    )
    commented_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["team__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "team"],
                name="unique_assignment_submission_per_team",
            )
        ]

    def __str__(self):
        return f"{self.assignment} / {self.team}"


class StudentAssignmentSubmission(TimeStampedModel):
    """개별과제에 대한 학생 단위 제출물."""

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="student_submissions",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="individual_assignment_submissions",
    )
    submission_url = models.URLField(blank=True)
    attachment = models.FileField(upload_to="student_submissions/", blank=True)
    note = models.TextField(blank=True)
    submitted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["student__user__first_name", "student__user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "student"],
                name="unique_assignment_submission_per_student",
            )
        ]

    def clean(self):
        super().clean()
        if self.assignment_id and self.assignment.assignment_type != Assignment.AssignmentType.INDIVIDUAL:
            raise ValidationError({"assignment": "개별과제에만 학생별 제출물을 저장할 수 있습니다."})

    def __str__(self):
        return f"{self.assignment} / {self.student}"


class EvaluationTemplate(TimeStampedModel):
    class EvaluationType(models.TextChoices):
        TEAM = "team", "팀 평가"
        PERSONAL = "personal", "개인 평가"

    name = models.CharField(max_length=120)
    evaluation_type = models.CharField(max_length=20, choices=EvaluationType.choices)
    evaluation_round = models.ForeignKey(
        EvaluationRound,
        on_delete=models.CASCADE,
        related_name="evaluation_templates",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["evaluation_type", "name"]

    def __str__(self):
        return self.name


class EvaluationCriterion(TimeStampedModel):
    template = models.ForeignKey(
        EvaluationTemplate,
        on_delete=models.CASCADE,
        related_name="criteria",
    )
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=1)
    max_score = models.PositiveSmallIntegerField(default=5)
    is_required = models.BooleanField(default=True)

    class Meta:
        ordering = ["template", "order", "id"]

    def __str__(self):
        return f"{self.template.name} - {self.title}"


class TeamEvaluation(TimeStampedModel):
    evaluation_round = models.ForeignKey(
        EvaluationRound,
        on_delete=models.CASCADE,
        related_name="team_evaluations",
    )
    evaluator = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="team_evaluations_given",
    )
    target_team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="team_evaluations_received",
    )
    comment = models.TextField(blank=True)
    is_submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation_round", "evaluator", "target_team"],
                name="unique_team_evaluation",
            )
        ]

    def __str__(self):
        return f"{self.evaluator} → {self.target_team}"


class TeamEvaluationScore(models.Model):
    evaluation = models.ForeignKey(
        TeamEvaluation,
        on_delete=models.CASCADE,
        related_name="scores",
    )
    criterion = models.ForeignKey(
        EvaluationCriterion,
        on_delete=models.PROTECT,
        related_name="team_scores",
    )
    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation", "criterion"],
                name="unique_team_criterion_score",
            )
        ]


class PersonalEvaluation(TimeStampedModel):
    evaluation_round = models.ForeignKey(
        EvaluationRound,
        on_delete=models.CASCADE,
        related_name="personal_evaluations",
    )
    evaluator = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="personal_evaluations_given",
    )
    target_student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="personal_evaluations_received",
    )
    comment = models.TextField(blank=True)
    is_submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation_round", "evaluator", "target_student"],
                name="unique_personal_evaluation",
            )
        ]

    def __str__(self):
        return f"{self.evaluator} → {self.target_student}"


class PersonalEvaluationScore(models.Model):
    evaluation = models.ForeignKey(
        PersonalEvaluation,
        on_delete=models.CASCADE,
        related_name="scores",
    )
    criterion = models.ForeignKey(
        EvaluationCriterion,
        on_delete=models.PROTECT,
        related_name="personal_scores",
    )
    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation", "criterion"],
                name="unique_personal_criterion_score",
            )
        ]


class RoundAttendance(TimeStampedModel):
    """평가 회차별 발표 당일 출결/참여 상태."""

    class Status(models.TextChoices):
        PRESENT = "present", "출석"
        ABSENT = "absent", "결석"
        EXCUSED = "excused", "공결"

    evaluation_round = models.ForeignKey(
        EvaluationRound,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="round_attendance_records",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PRESENT)
    note = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ["evaluation_round", "student__user__first_name", "student__user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation_round", "student"],
                name="unique_round_attendance",
            )
        ]

    @property
    def can_team_evaluate(self):
        return self.status == self.Status.PRESENT

    @property
    def can_personal_evaluate(self):
        return True

    def __str__(self):
        return f"{self.evaluation_round.name} / {self.student} / {self.get_status_display()}"


class TeamResult(TimeStampedModel):
    evaluation_round = models.ForeignKey(
        EvaluationRound,
        on_delete=models.CASCADE,
        related_name="team_results",
    )
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="results")
    score = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    rank = models.PositiveIntegerField(null=True, blank=True)
    is_excluded = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation_round", "team"],
                name="unique_team_result",
            )
        ]


class StudentResult(TimeStampedModel):
    evaluation_round = models.ForeignKey(
        EvaluationRound,
        on_delete=models.CASCADE,
        related_name="student_results",
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="results")
    team_score = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    personal_score = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    base_score = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    adjustment_score = models.DecimalField(max_digits=30, decimal_places=2, default=0)
    adjustment_reason = models.TextField(blank=True)
    final_score = models.DecimalField(max_digits=30, decimal_places=2, default=0)
    rank = models.PositiveIntegerField(null=True, blank=True)
    is_excluded = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation_round", "student"],
                name="unique_student_result",
            )
        ]


class AssignmentSkillImpact(TimeStampedModel):
    """종료된 기본 과제 평가가 수강생 역량 프로필에 반영된 이력."""

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="skill_impacts",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="assignment_skill_impacts",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="assignment_impacts",
    )
    performance_score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    skill_weight = models.PositiveSmallIntegerField(default=100)
    previous_score = models.SmallIntegerField(default=0)
    new_score = models.SmallIntegerField(default=0)
    applied_delta = models.SmallIntegerField(default=0)

    class Meta:
        ordering = ["-updated_at", "assignment_id", "skill__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "student", "skill"],
                name="unique_assignment_student_skill_impact",
            )
        ]

    def __str__(self):
        return f"{self.assignment} / {self.student} / {self.skill}: {self.applied_delta:+d}"


class HRTask(TimeStampedModel):
    """수강생 역량 기반으로 배정하는 성장 과제."""

    class Status(models.TextChoices):
        UNASSIGNED = "unassigned", "할당 전"
        SCHEDULED = "scheduled", "진행 예정"
        IN_PROGRESS = "in_progress", "진행 중"
        REVIEW = "review", "검토 요청"
        COMPLETED = "completed", "완료"

    class Priority(models.TextChoices):
        LOW = "low", "낮음"
        NORMAL = "normal", "보통"
        HIGH = "high", "높음"
        URGENT = "urgent", "긴급"

    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    attachment = models.FileField(upload_to="growth_tasks/", blank=True)
    evaluation_round = models.ForeignKey(
        EvaluationRound,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hr_tasks",
        help_text="연결하면 이 과제 평가가 해당 회차의 배지 산정에 반영됩니다.",
    )
    assignee = models.ForeignKey(
        Student,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hr_tasks",
    )
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNASSIGNED)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hr_tasks_created",
    )

    class Meta:
        ordering = ["status", "due_date", "-created_at"]

    @property
    def is_overdue(self):
        return bool(
            self.due_date
            and self.status != self.Status.COMPLETED
            and self.due_date < timezone.localdate()
        )

    @property
    def progress_percent(self):
        steps = list(self.steps.all())
        if not steps:
            return 0
        completed = sum(1 for step in steps if step.is_completed)
        return round((completed / len(steps)) * 100)

    @property
    def completed_step_count(self):
        return sum(1 for step in self.steps.all() if step.is_completed)

    @property
    def step_count(self):
        return len(self.steps.all())

    def clean(self):
        super().clean()
        if self.start_date and self.due_date and self.due_date < self.start_date:
            raise ValidationError("마감일은 시작일보다 빠를 수 없습니다.")

    def __str__(self):
        return self.title


class HRTaskStep(TimeStampedModel):
    """수강생이 순서대로 수행하는 과제 단계."""

    task = models.ForeignKey(HRTask, on_delete=models.CASCADE, related_name="steps")
    title = models.CharField(max_length=160)
    detail = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=1)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["task", "order"],
                name="unique_hr_task_step_order",
            )
        ]

    def __str__(self):
        return f"{self.task} / {self.order}. {self.title}"


class HRTaskSkill(TimeStampedModel):
    """과제 수행에 필요한 Skill과 중요도."""

    task = models.ForeignKey(HRTask, on_delete=models.CASCADE, related_name="required_skills")
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="required_by_tasks")
    weight = models.PositiveSmallIntegerField(
        default=100,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
    )

    class Meta:
        ordering = ["-weight", "skill__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["task", "skill"],
                name="unique_hr_task_skill",
            )
        ]

    def __str__(self):
        return f"{self.task} / {self.skill}: {self.weight}%"


class HRTaskSubmission(TimeStampedModel):
    """수강생이 역량 과제를 제출한 기록."""

    task = models.OneToOneField(
        HRTask,
        on_delete=models.CASCADE,
        related_name="submission",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="hr_task_submissions",
    )
    content = models.TextField(blank=True)
    attachment = models.FileField(upload_to="hr_task_submissions/", blank=True)
    submitted_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.task} / {self.student}"


class HRTaskEvaluation(TimeStampedModel):
    """관리자가 제출된 HR 과제를 검토/평가한 결과."""

    task = models.OneToOneField(
        HRTask,
        on_delete=models.CASCADE,
        related_name="evaluation",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="hr_task_evaluations",
    )
    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    comment = models.TextField(blank=True)
    evaluated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hr_task_evaluations",
    )
    evaluated_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.task} / {self.score}점"


class HRTaskSkillUpdate(TimeStampedModel):
    """역량 과제 평가가 수강생 역량 프로필에 반영된 이력."""

    task = models.ForeignKey(
        HRTask,
        on_delete=models.CASCADE,
        related_name="skill_updates",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="hr_task_skill_updates",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="hr_task_updates",
    )
    previous_score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    new_score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    task_score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    skill_weight = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["task", "skill"],
                name="unique_hr_task_skill_update",
            )
        ]

    @property
    def delta(self):
        return self.new_score - self.previous_score

    def __str__(self):
        return f"{self.task} / {self.skill}: {self.previous_score} → {self.new_score}"


class StudentBadge(TimeStampedModel):
    class BadgeType(models.TextChoices):
        MVP = "mvp", "MVP"
        GROWTH = "growth", "성장왕"
        CONSISTENT = "consistent", "연속 우수"

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="badges",
    )
    evaluation_round = models.ForeignKey(
        EvaluationRound,
        on_delete=models.CASCADE,
        related_name="student_badges",
    )
    badge_type = models.CharField(max_length=20, choices=BadgeType.choices)
    awarded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-awarded_at", "badge_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "evaluation_round", "badge_type"],
                name="unique_student_round_badge",
            )
        ]

    def __str__(self):
        return f"{self.student} - {self.get_badge_type_display()} ({self.evaluation_round})"


class AdminStudentComment(TimeStampedModel):
    """관리자가 평가 회차별로 학생에게 남기는 개인 피드백."""

    evaluation_round = models.ForeignKey(
        EvaluationRound,
        on_delete=models.CASCADE,
        related_name="admin_student_comments",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="admin_comments",
    )
    comment = models.TextField(max_length=2000)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_comments_created",
    )
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-evaluation_round__start_at", "-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation_round", "student"],
                name="unique_admin_comment_per_round_student",
            )
        ]

    def __str__(self):
        return f"{self.evaluation_round.name} / {self.student.name} 관리자 피드백"


class SelfProjectReview(TimeStampedModel):
    """학생이 종료된 프로젝트 회차를 스스로 회고하는 자기평가."""

    evaluation_round = models.ForeignKey(
        EvaluationRound,
        on_delete=models.CASCADE,
        related_name="self_project_reviews",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="self_project_reviews",
    )
    satisfaction = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="프로젝트 만족도",
    )
    contribution = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="체감 기여도",
    )
    collaboration = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="협업 만족도",
    )
    difficulty = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="프로젝트 난이도",
    )
    learned = models.TextField(blank=True, max_length=2000, verbose_name="배운 점")
    regret = models.TextField(blank=True, max_length=2000, verbose_name="아쉬운 점")
    next_action = models.TextField(blank=True, max_length=2000, verbose_name="다음 프로젝트에서 바꾸고 싶은 점")

    class Meta:
        ordering = ["-evaluation_round__start_at", "student"]
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation_round", "student"],
                name="unique_self_project_review_per_round_student",
            )
        ]

    def clean(self):
        super().clean()
        if self.evaluation_round_id and self.evaluation_round.status != EvaluationRound.Status.ENDED:
            raise ValidationError("프로젝트 자기평가는 종료된 회차에서만 작성할 수 있습니다.")

    def __str__(self):
        return f"{self.evaluation_round.name} / {self.student.name} 자기평가"


class ResultPublishSetting(TimeStampedModel):
    evaluation_round = models.OneToOneField(
        EvaluationRound,
        on_delete=models.CASCADE,
        related_name="publish_setting",
    )
    is_published = models.BooleanField(default=False)
    publish_at = models.DateTimeField(null=True, blank=True)
    show_team_first_place = models.BooleanField(default=True)
    show_all_team_ranks = models.BooleanField(default=True)
    show_personal_score = models.BooleanField(default=True)
    show_overall_rank = models.BooleanField(default=True)
    show_comments = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.evaluation_round.name} 결과 공개 설정"


class Announcement(TimeStampedModel):
    class Priority(models.TextChoices):
        NORMAL = "normal", "일반"
        IMPORTANT = "important", "중요"
        URGENT = "urgent", "긴급"

    title = models.CharField(max_length=160)
    body = models.TextField()
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    is_published = models.BooleanField(default=True)
    publish_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="announcements_created")
    # 전체 공지면 True, 특정 학생에게만 보내는 내부 메시지면 False.
    target_all = models.BooleanField(default=True)
    recipients = models.ManyToManyField(
        Student,
        blank=True,
        related_name="targeted_announcements",
    )

    class Meta:
        ordering = ["-publish_at", "-id"]

    def __str__(self):
        return self.title


class AnnouncementRead(TimeStampedModel):
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="reads")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="announcement_reads")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["announcement", "student"], name="unique_announcement_read")
        ]


class InternalMessage(TimeStampedModel):
    class Priority(models.TextChoices):
        NORMAL = "normal", "일반"
        IMPORTANT = "important", "중요"
        URGENT = "urgent", "긴급"

    recipient = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="internal_messages")
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="internal_messages_sent")
    title = models.CharField(max_length=160)
    body = models.TextField()
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    read_at = models.DateTimeField(null=True, blank=True)
    recalled_at = models.DateTimeField(null=True, blank=True)
    admin_deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    @property
    def is_read(self):
        return self.read_at is not None

    def __str__(self):
        return f"{self.recipient.name} / {self.title}"


class AdminActivityLog(models.Model):
    """관리자 화면에서 발생한 변경 작업을 남기는 감사 로그."""

    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_activity_logs",
    )
    action_key = models.CharField(max_length=80, db_index=True)
    action_label = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    path = models.CharField(max_length=500)
    target_type = models.CharField(max_length=80, blank=True)
    target_id = models.CharField(max_length=80, blank=True)
    ip_address = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        actor = self.actor.get_username() if self.actor else "unknown"
        return f"{self.created_at:%Y-%m-%d %H:%M} {actor} {self.action_label}"
