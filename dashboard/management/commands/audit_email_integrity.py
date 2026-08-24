from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from django.db.models.functions import Lower


class Command(BaseCommand):
    help = "로그인에 사용되는 이메일의 중복/충돌 여부를 읽기 전용으로 점검합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fail-on-duplicates",
            action="store_true",
            help="중복 이메일이 있으면 종료 코드 1로 실패 처리합니다.",
        )

    def handle(self, *args, **options):
        User = get_user_model()

        duplicate_rows = list(
            User.objects.exclude(email="")
            .annotate(normalized_email=Lower("email"))
            .values("normalized_email")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
            .order_by("normalized_email")
        )

        username_collision_rows = []
        email_users = list(
            User.objects.exclude(email="")
            .values("id", "username", "email")
            .order_by("id")
        )
        usernames = {
            row["username"].strip().lower(): row["id"]
            for row in User.objects.exclude(username="").values("id", "username")
        }
        for row in email_users:
            normalized = row["email"].strip().lower()
            owner_id = usernames.get(normalized)
            if owner_id and owner_id != row["id"]:
                username_collision_rows.append(
                    {
                        "email": row["email"],
                        "email_user_id": row["id"],
                        "username_user_id": owner_id,
                    }
                )

        if not duplicate_rows:
            self.stdout.write(self.style.SUCCESS("중복 이메일 없음"))
        else:
            self.stdout.write(self.style.ERROR(f"중복 이메일 {len(duplicate_rows)}개 발견"))
            for row in duplicate_rows:
                email = row["normalized_email"]
                users = list(
                    User.objects.filter(email__iexact=email)
                    .values_list("id", "username")
                    .order_by("id")
                )
                detail = ", ".join(f"id={user_id}:{username}" for user_id, username in users)
                self.stdout.write(f"- {email}: {row['count']}개 ({detail})")

        if not username_collision_rows:
            self.stdout.write(self.style.SUCCESS("이메일↔다른 계정 username 충돌 없음"))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"이메일↔다른 계정 username 충돌 {len(username_collision_rows)}건"
                )
            )
            for row in username_collision_rows:
                self.stdout.write(
                    f"- {row['email']} (email user={row['email_user_id']}, "
                    f"username user={row['username_user_id']})"
                )

        if duplicate_rows and options["fail_on_duplicates"]:
            raise CommandError("중복 이메일이 있어 로그인 이메일 유일성을 보장할 수 없습니다.")
