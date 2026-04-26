"""Convert bars_bar to a TimescaleDB hypertable on `ts` (Postgres + Timescale).

Skipped on:
  * non-Postgres backends (SQLite test runner)
  * Postgres instances where the timescaledb extension is not installable
    (e.g. plain managed Postgres on Railway / Supabase / etc.)
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
    if not _has_timescale(schema_editor):
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
