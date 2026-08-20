from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Student


class StudentSelfSignupTests(TestCase):
    def test_signup_page_opens(self):
        response = self.client.get(reverse("signup"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "수강생 회원가입")

    def test_student_can_create_own_id_and_login_immediately(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "my_student_id",
                "name": "테스트 학생",
                "email": "student@example.com",
                "password1": "AxStudent!2026",
                "password2": "AxStudent!2026",
            },
        )

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="my_student_id")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password("AxStudent!2026"))
        self.assertTrue(Student.objects.filter(user=user, is_active=True).exists())
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.id)

    def test_duplicate_username_is_rejected(self):
        User.objects.create_user(username="taken_id", password="Existing!2026")
        response = self.client.post(
            reverse("signup"),
            {
                "username": "taken_id",
                "name": "중복 학생",
                "email": "",
                "password1": "AxStudent!2026",
                "password2": "AxStudent!2026",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "이미 사용 중인 아이디입니다")
        self.assertEqual(User.objects.filter(username="taken_id").count(), 1)

    def test_duplicate_email_is_rejected_for_safe_social_linking(self):
        User.objects.create_user(
            username="existing_student",
            email="same@example.com",
            password="Existing!2026",
        )
        response = self.client.post(
            reverse("signup"),
            {
                "username": "new_student",
                "name": "새 학생",
                "email": "SAME@example.com",
                "password1": "AxStudent!2026",
                "password2": "AxStudent!2026",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "이미 등록된 이메일입니다")
        self.assertFalse(User.objects.filter(username="new_student").exists())

    def test_password_confirmation_must_match(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "student_mismatch",
                "name": "비밀번호 학생",
                "email": "",
                "password1": "AxStudent!2026",
                "password2": "Different!2026",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "비밀번호가 서로 일치하지 않습니다")
        self.assertFalse(User.objects.filter(username="student_mismatch").exists())
