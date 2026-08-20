from django.db import connection

RAW_TABLE = "dashboard_officialevaluationresponse"


def official_response_counts(evaluation_round):
    """Return raw official-import response counts for a round, or None if not imported."""
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

    total = sum(counts.values())
    if total <= 0:
        return None

    return {
        "team": counts.get("team", 0),
        "personal": counts.get("personal", 0),
        "total": total,
    }
