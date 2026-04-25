"""Convert runs_equitypoint to a TimescaleDB hypertable on `ts` (Postgres only)."""

from django.db import migrations


def make_hypertable(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
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
