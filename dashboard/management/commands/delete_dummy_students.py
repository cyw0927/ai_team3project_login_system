from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction


class Command(BaseCommand):
    help = "student01, student02 같은 더미 학생 계정을 모두 삭제합니다."

    @transaction.atomic
    def handle(self, *args, **options):

        dummy_users = User.objects.filter(
            username__regex=r"^student[0-9]{2}$"
        )

        count = dummy_users.count()

        if count == 0:
            self.stdout.write(
                self.style.WARNING("삭제할 더미 학생이 없습니다.")
            )
            return

        self.stdout.write(f"삭제 대상: {count}명")

        for user in dummy_users:
            self.stdout.write(f"- {user.username}")

        # User 삭제 시 연결된 Student 및 관련 CASCADE 데이터도 함께 삭제
        dummy_users.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"더미 학생 {count}명 삭제 완료!"
            )
        )
