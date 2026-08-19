from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "PostgreSQL 접속 및 practice search_path 설정을 비밀번호 노출 없이 확인합니다."

    def handle(self, *args, **options):
        cfg = settings.DATABASES["default"]
        self.stdout.write("=== AX PostgreSQL 설정 점검 ===")
        self.stdout.write(f"ENGINE : {cfg.get('ENGINE')}")
        self.stdout.write(f"NAME   : {cfg.get('NAME')}")
        self.stdout.write(f"USER   : {cfg.get('USER')}")
        self.stdout.write(f"HOST   : {cfg.get('HOST')}")
        self.stdout.write(f"PORT   : {cfg.get('PORT')}")
        self.stdout.write(f"SCHEMA : {getattr(settings, 'DB_SCHEMA', 'practice')}")
        self.stdout.write(f"PASSWORD SET: {'YES' if bool(cfg.get('PASSWORD')) else 'NO'}")
        self.stdout.write("")
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_database(), current_user, current_schema(), "
                    "current_setting('search_path')"
                )
                database, user, schema, search_path = cursor.fetchone()
            self.stdout.write(self.style.SUCCESS("PostgreSQL CONNECTION: OK"))
            self.stdout.write(f"current_database: {database}")
            self.stdout.write(f"current_user    : {user}")
            self.stdout.write(f"current_schema  : {schema}")
            self.stdout.write(f"search_path     : {search_path}")
        except Exception as exc:
            self.stdout.write(self.style.ERROR("PostgreSQL CONNECTION: FAILED"))
            self.stdout.write(".env의 DB_PASSWORD/DB_HOST/DB_PORT와 PostgreSQL 실행 상태를 확인하세요.")
            raise CommandError(f"{exc.__class__.__name__}: {exc}") from exc
