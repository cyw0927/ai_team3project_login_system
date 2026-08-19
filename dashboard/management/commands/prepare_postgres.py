import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Command(BaseCommand):
    help = "PostgreSQL practice 스키마를 준비하고 search_path를 점검합니다."

    def handle(self, *args, **options):
        schema = getattr(settings, "DB_SCHEMA", "practice")
        if not _SCHEMA_RE.fullmatch(schema):
            raise CommandError(f"허용되지 않는 DB_SCHEMA 이름입니다: {schema!r}")

        try:
            with connection.cursor() as cursor:
                quoted = connection.ops.quote_name(schema)
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {quoted}")
                cursor.execute("SELECT current_database(), current_user, current_setting('search_path')")
                database, user, search_path = cursor.fetchone()
        except Exception as exc:
            raise CommandError(f"PostgreSQL 준비 실패: {exc.__class__.__name__}: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("PostgreSQL schema 준비 완료"))
        self.stdout.write(f"database   : {database}")
        self.stdout.write(f"user       : {user}")
        self.stdout.write(f"schema     : {schema}")
        self.stdout.write(f"search_path: {search_path}")
