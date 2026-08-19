from django import forms
from django.contrib.auth.models import User

from .models import Assignment, EvaluationCriterion, EvaluationRound, EvaluationTemplate, SelfProjectReview, Student, Team


class StudentCreateForm(forms.Form):
    name = forms.CharField(max_length=150, label="이름")
    email = forms.EmailField(required=False, label="이메일")
    password = forms.CharField(
        min_length=8,
        required=False,
        label="임시 비밀번호",
        widget=forms.PasswordInput,
        help_text="로그인이 필요한 수강생만 입력하세요.",
    )
    affiliation = forms.CharField(max_length=100, required=False, label="소속")
    team_id = forms.ModelChoiceField(
        queryset=Team.objects.none(),
        required=False,
        label="팀",
        empty_label="미배정",
    )
    is_active = forms.BooleanField(required=False, initial=True, label="활성")

    def __init__(self, *args, teams=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["team_id"].queryset = teams if teams is not None else Team.objects.none()

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if email and (
            User.objects.filter(email__iexact=email).exists()
            or User.objects.filter(username__iexact=email).exists()
        ):
            raise forms.ValidationError("이미 등록된 이메일입니다.")
        return email


class StudentUpdateForm(forms.Form):
    name = forms.CharField(max_length=150, label="이름")
    email = forms.EmailField(required=False, label="이메일")
    password = forms.CharField(
        min_length=8,
        required=False,
        label="새 비밀번호",
        widget=forms.PasswordInput,
        help_text="변경할 때만 입력하세요.",
    )
    affiliation = forms.CharField(max_length=100, required=False, label="소속")
    team_id = forms.ModelChoiceField(
        queryset=Team.objects.none(),
        required=False,
        label="팀",
        empty_label="미배정",
    )
    is_active = forms.BooleanField(required=False, label="활성")

    def __init__(self, *args, student=None, teams=None, **kwargs):
        self.student = student
        super().__init__(*args, **kwargs)
        self.fields["team_id"].queryset = teams if teams is not None else Team.objects.none()

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            return ""
        qs = User.objects.filter(email__iexact=email) | User.objects.filter(username__iexact=email)
        if self.student:
            qs = qs.exclude(pk=self.student.user_id)
        if qs.exists():
            raise forms.ValidationError("이미 등록된 이메일입니다.")
        return email


class EvaluationRoundForm(forms.ModelForm):
    start_at = forms.DateTimeField(
        label="시작 일시",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )
    end_at = forms.DateTimeField(
        label="종료 일시",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )

    class Meta:
        model = EvaluationRound
        fields = ["name", "start_at", "end_at"]

    def clean(self):
        cleaned = super().clean()
        start_at = cleaned.get("start_at")
        end_at = cleaned.get("end_at")
        if start_at and end_at and end_at <= start_at:
            raise forms.ValidationError("종료 일시는 시작 일시보다 뒤여야 합니다.")
        return cleaned


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ["evaluation_round", "assignment_type", "title", "description", "attachment"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, rounds=None, **kwargs):
        super().__init__(*args, **kwargs)
        if rounds is not None:
            self.fields["evaluation_round"].queryset = rounds
        self.fields["evaluation_round"].empty_label = "평가 회차를 선택하세요."

    def clean(self):
        cleaned = super().clean()
        evaluation_round = cleaned.get("evaluation_round")
        assignment_type = cleaned.get("assignment_type")
        if evaluation_round and assignment_type:
            qs = Assignment.objects.filter(
                evaluation_round=evaluation_round,
                assignment_type=assignment_type,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                label = dict(Assignment.AssignmentType.choices).get(assignment_type, assignment_type)
                raise forms.ValidationError(f"이 회차에는 이미 {label}가 등록되어 있습니다.")
        return cleaned


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ["evaluation_round", "name", "project_title", "is_active"]

    def __init__(self, *args, rounds=None, **kwargs):
        super().__init__(*args, **kwargs)
        if rounds is not None:
            self.fields["evaluation_round"].queryset = rounds
        self.fields["evaluation_round"].empty_label = "평가 회차를 선택하세요."

    def clean(self):
        cleaned = super().clean()
        evaluation_round = cleaned.get("evaluation_round")
        name = (cleaned.get("name") or "").strip()
        if evaluation_round and name:
            qs = Team.objects.filter(evaluation_round=evaluation_round, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("같은 평가 회차에 동일한 팀명이 이미 존재합니다.")
        return cleaned


class EvaluationTemplateForm(forms.ModelForm):
    class Meta:
        model = EvaluationTemplate
        fields = ["name", "evaluation_type", "evaluation_round", "is_active"]

    def __init__(self, *args, rounds=None, **kwargs):
        super().__init__(*args, **kwargs)
        if rounds is not None:
            self.fields["evaluation_round"].queryset = rounds
        self.fields["evaluation_round"].required = False
        self.fields["evaluation_round"].empty_label = "공통 템플릿 (회차 미지정)"


class EvaluationCriterionForm(forms.ModelForm):
    max_score = forms.IntegerField(min_value=1, max_value=5, initial=5, label="최대 점수")

    class Meta:
        model = EvaluationCriterion
        fields = ["title", "description", "order", "max_score", "is_required"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class StudentProfileForm(forms.Form):
    name = forms.CharField(max_length=150, label="이름")
    affiliation = forms.CharField(max_length=100, required=False, label="소속")

    def __init__(self, *args, student=None, **kwargs):
        self.student = student
        initial = kwargs.setdefault("initial", {})
        if student:
            initial.setdefault("name", student.name)
            initial.setdefault("affiliation", student.affiliation)
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("이름을 입력해 주세요.")
        return name


class SelfProjectReviewForm(forms.ModelForm):
    SCORE_CHOICES = [(i, f"{i}점") for i in range(1, 6)]

    satisfaction = forms.TypedChoiceField(label="프로젝트 만족도", choices=SCORE_CHOICES, coerce=int)
    contribution = forms.TypedChoiceField(label="내 기여도", choices=SCORE_CHOICES, coerce=int)
    collaboration = forms.TypedChoiceField(label="협업 만족도", choices=SCORE_CHOICES, coerce=int)
    difficulty = forms.TypedChoiceField(label="프로젝트 난이도", choices=SCORE_CHOICES, coerce=int)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("satisfaction", "contribution", "collaboration", "difficulty"):
            self.fields[name].widget.attrs.update({"class": "form-select"})
        for name in ("learned", "regret", "next_action"):
            self.fields[name].widget.attrs.update({"class": "form-control"})

    class Meta:
        model = SelfProjectReview
        fields = [
            "satisfaction", "contribution", "collaboration", "difficulty",
            "learned", "regret", "next_action",
        ]
        widgets = {
            "learned": forms.Textarea(attrs={"rows": 3, "placeholder": "이번 프로젝트에서 새롭게 배운 점을 적어주세요."}),
            "regret": forms.Textarea(attrs={"rows": 3, "placeholder": "아쉽거나 개선하고 싶은 점을 적어주세요."}),
            "next_action": forms.Textarea(attrs={"rows": 3, "placeholder": "다음 프로젝트에서 바꾸고 싶은 행동을 적어주세요."}),
        }
