"""Convert runs_equitypoint to a TimescaleDB hypertable on `ts`.

Skipped on non-Postgres backends and on Postgres instances without
the timescaledb extension (e.g. Railway managed Postgres).
"""

from django.db import migrations


def _has_timescale(schema_editor) -> bool:
    cursor = schema_editor.connection.cursor()
    cursor.execute(
        "SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb' LIMIT 1;"
    )
    return cursor.fetchone() is not None


def make_hypertable(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    if not _has_timescale(schema_editor):
        return
    schema_editor.execute("ALTER TABLE runs_equitypoint DROP CONSTRAINT runs_equitypoint_pkey;")
    schema_editor.execute(
        "ALTER TABLE runs_equitypoint ADD CONSTRAINT runs_equitypoint_pkey PRIMARY KEY (id, ts);"
    )
    schema_editor.execute(
        "SELECT create_hypertable("
        "    'runs_equitypoint',"
        "    by_range('ts', INTERVAL '365 days'),"
        "    if_not_exists => TRUE,"
        "    migrate_data  => TRUE"
        ");"
    )


def revert_hypertable(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    if not _has_timescale(schema_editor):
        return
    schema_editor.execute(
        "SELECT drop_chunks('runs_equitypoint', older_than => NOW() + INTERVAL '100 years');"
    )
    schema_editor.execute("ALTER TABLE runs_equitypoint DROP CONSTRAINT runs_equitypoint_pkey;")
    schema_editor.execute(
        "ALTER TABLE runs_equitypoint ADD CONSTRAINT runs_equitypoint_pkey PRIMARY KEY (id);"
    )


class Migration(migrations.Migration):
    dependencies = [("runs", "0001_initial")]

    operations = [
        migrations.RunPython(make_hypertable, reverse_code=revert_hypertable),
    ]
