import json

from django.db import connection

from dashboard.management.commands.reset_and_import_ax2_data_v2 import Command as V2Command
from dashboard.models import Student


class Command(V2Command):
    help = (
        "AX2 최종 재구축 명령. 팀이 다른 동일 별칭을 A/B 학생으로 분리하고, "
        "원본 응답은 보존하면서 실제 미제출 조합이 관리자 화면에 나타나게 합니다."
    )

    @staticmethod
    def _insert_raw_rows(evaluation_round_id, source):
        # legacy 코드가 response_type=team/personal 원본을 '전원 완료된 과거 import'로
        # 오인하지 않도록 source 타입으로 보존한다. payload 자체는 한 글자도 바꾸지 않는다.
        raw_type = f"{source['type']}_source"
        sql = """
            INSERT INTO dashboard_officialevaluationresponse
                (evaluation_round_id, response_type, source_filename, source_sha256, source_row, payload)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        """
        params = [
            (
                evaluation_round_id,
                raw_type,
                source["filename"],
                source["sha256"],
                item["source_row"],
                json.dumps(item["payload"], ensure_ascii=False),
            )
            for item in source["rows"]
        ]
        with connection.cursor() as cursor:
            cursor.executemany(sql, params)

    @staticmethod
    def _create_participants_and_teams(evaluation_round, projection):
        students, teams = V2Command._create_participants_and_teams(
            evaluation_round, projection
        )
        Student.objects.filter(id__in=[student.id for student in students.values()]).update(
            affiliation="AX2 공식 재구축 데이터"
        )
        return students, teams
