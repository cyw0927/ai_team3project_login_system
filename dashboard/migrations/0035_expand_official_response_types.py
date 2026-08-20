from django.db import migrations


FORWARD_SQL = r"""
DO $$
DECLARE
    constraint_name text;
BEGIN
    SELECT conname INTO constraint_name
    FROM pg_constraint
    WHERE conrelid = 'dashboard_officialevaluationresponse'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%response_type%';

    IF constraint_name IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE dashboard_officialevaluationresponse DROP CONSTRAINT %I',
            constraint_name
        );
    END IF;
END $$;

ALTER TABLE dashboard_officialevaluationresponse
ADD CONSTRAINT dashboard_official_eval_response_type_check
CHECK (response_type IN ('personal', 'team', 'personal_source', 'team_source'));
"""


REVERSE_SQL = r"""
UPDATE dashboard_officialevaluationresponse
SET response_type = CASE response_type
    WHEN 'personal_source' THEN 'personal'
    WHEN 'team_source' THEN 'team'
    ELSE response_type
END;

ALTER TABLE dashboard_officialevaluationresponse
DROP CONSTRAINT IF EXISTS dashboard_official_eval_response_type_check;

ALTER TABLE dashboard_officialevaluationresponse
ADD CONSTRAINT dashboard_official_eval_response_type_check
CHECK (response_type IN ('personal', 'team'));
"""


class Migration(migrations.Migration):
    dependencies = [
        ('dashboard', '0034_official_evaluation_import_raw'),
    ]

    operations = [
        migrations.RunSQL(FORWARD_SQL, reverse_sql=REVERSE_SQL),
    ]
