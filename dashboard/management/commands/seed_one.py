from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from dashboard.models import Student


class Command(BaseCommand):
    help = "테스트용 관리자 1명과 수강생 1명을 생성하거나 기존 데이터를 갱신합니다."

    @transaction.atomic
    def handle(self, *args, **options):
        # -------------------------
        # 관리자 계정
        # -------------------------
        admin_username = "admin01"
        admin_email = "admin01@example.com"
        admin_password = "admin1234!"
        admin_name = "관리자테스트"

        admin_user, admin_created = User.objects.get_or_create(
            username=admin_username,
            defaults={
                "email": admin_email,
                "first_name": admin_name,
                "is_active": True,
                "is_staff": True,
                "is_superuser": True,
            },
        )

        admin_user.email = admin_email
        admin_user.first_name = admin_name
        admin_user.last_name = ""
        admin_user.is_active = True
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.set_password(admin_password)
        admin_user.save()

        # 관리자 계정에 수강생 프로필이 잘못 붙어 있다면 제거합니다.
        Student.objects.filter(user=admin_user).delete()

        # -------------------------
        # 수강생 계정
        # -------------------------
        student_username = "test01"
        student_email = "test01@example.com"
        student_password = "test1234!"
        student_name = "김테스트"
        student_affiliation = "AI Agent"

        student_user, student_user_created = User.objects.get_or_create(
            username=student_username,
            defaults={
                "email": student_email,
                "first_name": student_name,
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
            },
        )

        student_user.email = student_email
        student_user.first_name = student_name
        student_user.last_name = ""
        student_user.is_active = True
        student_user.is_staff = False
        student_user.is_superuser = False
        student_user.set_password(student_password)
        student_user.save()

        student, student_created = Student.objects.get_or_create(
            user=student_user,
            defaults={
                "affiliation": student_affiliation,
                "is_active": True,
            },
        )

        student.affiliation = student_affiliation
        student.is_active = True
        student.save()

        # -------------------------
        # 결과 출력
        # -------------------------
        if admin_created:
            self.stdout.write(self.style.SUCCESS("더미 관리자 1명을 생성했습니다."))
        else:
            self.stdout.write(self.style.WARNING("기존 admin01 계정을 관리자 더미 값으로 갱신했습니다."))

        if student_user_created or student_created:
            self.stdout.write(self.style.SUCCESS("더미 수강생 1명을 생성했습니다."))
        else:
            self.stdout.write(self.style.WARNING("기존 test01 계정을 수강생 더미 값으로 갱신했습니다."))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("[관리자 로그인]"))
        self.stdout.write(f"  아이디: {admin_username}")
        self.stdout.write(f"  이메일: {admin_email}")
        self.stdout.write(f"  비밀번호: {admin_password}")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("[수강생 로그인]"))
        self.stdout.write(f"  아이디: {student_username}")
        self.stdout.write(f"  이메일: {student_email}")
        self.stdout.write(f"  비밀번호: {student_password}")
        self.stdout.write(f"  이름: {student_name}")
        self.stdout.write(f"  소속: {student_affiliation}")
