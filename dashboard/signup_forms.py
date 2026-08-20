from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Student


class StudentSignupForm(forms.Form):
    """수강생이 직접 만드는 일반 로그인 계정 회원가입 폼."""

    username = forms.CharField(
        label="아이디",
        min_length=4,
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "username"}),
    )
    name = forms.CharField(label="이름", max_length=150)
    email = forms.EmailField(label="이메일", required=False)
    password1 = forms.CharField(
        label="비밀번호",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="비밀번호 확인",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean_username(self):
        User = get_user_model()
        username = self.cleaned_data["username"].strip()

        # Django 기본 User username 규칙을 그대로 적용한다.
        field = User._meta.get_field("username")
        for validator in field.validators:
            validator(username)

        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("이미 사용 중인 아이디입니다.")
        return username

    def clean_email(self):
        User = get_user_model()
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("이미 등록된 이메일입니다. 기존 계정으로 로그인해주세요.")
        return email

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "비밀번호가 서로 일치하지 않습니다.")
            return cleaned

        if password1:
            User = get_user_model()
            candidate = User(
                username=cleaned.get("username", ""),
                email=cleaned.get("email", ""),
                first_name=cleaned.get("name", ""),
            )
            try:
                password_validation.validate_password(password1, candidate)
            except ValidationError as exc:
                self.add_error("password1", exc)

        return cleaned

    @transaction.atomic
    def save(self):
        User = get_user_model()
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            password=self.cleaned_data["password1"],
            email=self.cleaned_data.get("email", ""),
            first_name=self.cleaned_data["name"],
            last_name="",
        )
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.save(update_fields=["is_active", "is_staff", "is_superuser"])
        Student.objects.create(user=user, is_active=True)
        return user
