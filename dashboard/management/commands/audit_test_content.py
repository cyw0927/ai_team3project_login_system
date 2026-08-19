import re
from django.core.management.base import BaseCommand
from dashboard.models import AdminStudentComment, Announcement, Assignment, EvaluationRound, HRTask, InternalMessage, Student

SUSPICIOUS = re.compile(r"^(?:test|test\d+|dummy|dummy\d+|111+|222+|1234+|asdf|qwer|가나다|테스트)$", re.IGNORECASE)

class Command(BaseCommand):
    help = "사용자 화면에 노출될 수 있는 테스트성 문구/데이터를 읽기 전용으로 점검합니다."

    def handle(self, *args, **options):
        checks = [
            ("수강생 이름", Student.objects.select_related("user"), lambda x: x.name),
            ("회차명", EvaluationRound.objects.all(), lambda x: x.name),
            ("기본 과제", Assignment.objects.all(), lambda x: x.title),
            ("역량 과제", HRTask.objects.all(), lambda x: x.title),
            ("공지", Announcement.objects.all(), lambda x: x.title),
            ("메시지", InternalMessage.objects.all(), lambda x: x.subject),
            ("튜터 피드백", AdminStudentComment.objects.all(), lambda x: x.comment),
        ]
        total = 0
        for label, queryset, getter in checks:
            found = []
            for obj in queryset.iterator():
                value = (getter(obj) or "").strip()
                if SUSPICIOUS.match(value):
                    found.append((obj.pk, value))
            if found:
                total += len(found)
                self.stdout.write(self.style.WARNING(f"[{label}] {len(found)}건"))
                for pk, value in found[:20]:
                    self.stdout.write(f"  id={pk}: {value}")
        if total:
            self.stdout.write(self.style.WARNING(f"테스트성 데이터 후보 총 {total}건입니다. 자동 삭제/수정은 하지 않았습니다."))
        else:
            self.stdout.write(self.style.SUCCESS("눈에 띄는 테스트성 문구 후보가 없습니다."))
