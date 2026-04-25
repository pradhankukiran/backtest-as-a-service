"""Convert bars_bar to a TimescaleDB hypertable on `ts` (Postgres only).

The migration is a no-op on non-Postgres backends so the SQLite test runner
still works for unit tests that don't need time-series semantics.
"""

from django.db import migrations


def make_hypertable(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
    schema_editor.execute("ALTER TABLE bars_bar DROP CONSTRAINT bars_bar_pkey;")
    schema_editor.execute(
        "ALTER TABLE bars_bar ADD CONSTRAINT bars_bar_pkey PRIMARY KEY (id, ts);"
    )
    schema_editor.execute(
        "SELECT create_hypertable("
        "    'bars_bar',"
        "    by_range('ts', INTERVAL '365 days'),"
        "    if_not_exists => TRUE,"
        "    migrate_data  => TRUE"
        ");"
    )


def revert_hypertable(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "SELECT drop_chunks('bars_bar', older_than => NOW() + INTERVAL '100 years');"
    )
    schema_editor.execute("ALTER TABLE bars_bar DROP CONSTRAINT bars_bar_pkey;")
    schema_editor.execute(
        "ALTER TABLE bars_bar ADD CONSTRAINT bars_bar_pkey PRIMARY KEY (id);"
    )


class Migration(migrations.Migration):
    dependencies = [("bars", "0001_initial")]

    operations = [
        migrations.RunPython(make_hypertable, reverse_code=revert_hypertable),
    ]
