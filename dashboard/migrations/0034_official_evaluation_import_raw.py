from django.db import migrations


CREATE_SQL = r"""
CREATE TABLE dashboard_officialevaluationresponse (
    id BIGSERIAL PRIMARY KEY,
    evaluation_round_id BIGINT NOT NULL
        REFERENCES dashboard_evaluationround(id)
        ON DELETE CASCADE,
    response_type VARCHAR(20) NOT NULL
        CHECK (response_type IN ('personal', 'team')),
    source_filename VARCHAR(255) NOT NULL,
    source_sha256 VARCHAR(64) NOT NULL,
    source_row INTEGER NOT NULL,
    payload JSONB NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX dashboard_official_eval_round_idx
    ON dashboard_officialevaluationresponse (evaluation_round_id);
CREATE INDEX dashboard_official_eval_type_idx
    ON dashboard_officialevaluationresponse (response_type);
"""

DROP_SQL = r"""
DROP TABLE IF EXISTS dashboard_officialevaluationresponse;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0033_adminstudentcomment_read_at"),
    ]

    operations = [
        migrations.RunSQL(CREATE_SQL, reverse_sql=DROP_SQL),
    ]
