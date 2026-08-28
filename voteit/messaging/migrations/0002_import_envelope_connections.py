"""Copy rows from the channels-envelope Connection table into ours.

Deliberately uses raw SQL rather than ``apps.get_model("envelope", ...)``: the
envelope app is removed from INSTALLED_APPS in the same release, so the
historical model is not available and a replay on a fresh database would fail.
The existence check makes this a no-op on fresh installs and on --keepdb test
databases.

Dropping envelope_connection itself is left to a later release so this one
stays rollback-able.
"""

from django.db import migrations

ENVELOPE_TABLE = "envelope_connection"

TABLE_EXISTS = """
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = %s
    )
"""

SELECT_ROWS = f"""
    SELECT user_id, channel_name, online_at, last_action, offline_at, online
    FROM {ENVELOPE_TABLE}
"""


CHUNK_SIZE = 2000


def import_connections(apps, schema_editor):
    Connection = apps.get_model("voteit_messaging", "Connection")
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute(TABLE_EXISTS, [ENVELOPE_TABLE])
        if not cursor.fetchone()[0]:
            return

    # Streamed a chunk at a time: the legacy table is never reaped and runs to
    # ~10^6 rows in production, so a fetchall() would hold all of it in memory
    # and bulk_create() -- which list()s whatever it is handed -- would hold a
    # model instance per row on top of that. chunked_cursor() gives a
    # server-side cursor unless DISABLE_SERVER_SIDE_CURSORS is set, in which
    # case this degrades to the old memory profile but still works.
    with connection.chunked_cursor() as cursor:
        cursor.execute(SELECT_ROWS)
        while True:
            rows = cursor.fetchmany(CHUNK_SIZE)
            if not rows:
                break
            Connection.objects.bulk_create(
                [
                    Connection(
                        user_id=user_id,
                        channel_name=(channel_name or "")[:150],
                        connected_at=online_at,
                        # last_action was nullable on the old model; fall back
                        # to the disconnect time and finally to the connect
                        # time.
                        last_action=last_action or offline_at or online_at,
                        # The old data has no close code, so synthesise normal
                        # closure for anything already marked offline.
                        code=None if online else 1000,
                    )
                    for (
                        user_id,
                        channel_name,
                        online_at,
                        last_action,
                        offline_at,
                        online,
                    ) in rows
                ],
                batch_size=CHUNK_SIZE,
            )


def drop_imported(apps, schema_editor):
    apps.get_model("voteit_messaging", "Connection").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("voteit_messaging", "0001_initial")]

    operations = [migrations.RunPython(import_connections, drop_imported)]
