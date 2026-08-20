from django.db import connection

RAW_TABLE = "dashboard_officialevaluationresponse"


def official_response_counts(evaluation_round):
    """Return legacy completed-import counts, or None for corrected source archives."""
    if not evaluation_round:
        return None

    if RAW_TABLE not in connection.introspection.table_names():
        return None

    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT response_type, COUNT(*)
            FROM {quote(RAW_TABLE)}
            WHERE evaluation_round_id = %s
            GROUP BY response_type
            """,
            [evaluation_round.id],
        )
        counts = {response_type: count for response_type, count in cursor.fetchall()}

    # 예전 importer는 team/personal 타입을 '이미 완료된 데이터'로 간주했다.
    # corrected rebuild는 team_source/personal_source로 원본만 보관하므로
    # 실제 canonical 제출/미제출 계산을 사용해야 한다.
    team_count = counts.get("team", 0)
    personal_count = counts.get("personal", 0)
    total = team_count + personal_count
    if total <= 0:
        return None

    return {
        "team": team_count,
        "personal": personal_count,
        "total": total,
    }
