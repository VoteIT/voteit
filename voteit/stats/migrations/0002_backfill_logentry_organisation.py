"""
Backfill "m" and "o" in auditlog's additional_data, which the stats job now
attributes entries by. Older entries often only have "ai", or nothing at all.
"""

from django.db import migrations

# (app_label, model, FK column on the logged model, parent model with meeting_id)
VIA_PARENT = (
    ("meeting", "groupmembership", "meeting_group_id", "meeting.MeetingGroup"),
    ("invites", "meetinggroupannotation", "meeting_group_id", "meeting.MeetingGroup"),
    ("speaker", "speakersystemroles", "context_id", "speaker.SpeakerListSystem"),
    ("poll", "vote", "poll_id", "poll.Poll"),
)


def _key_id(key):
    # A few old entries hold a meeting title in "m".
    return (
        f"CASE WHEN jsonb_typeof(le.additional_data->'{key}') = 'number' "
        f"THEN (le.additional_data->>'{key}')::bigint END"
    )


def _set_key(cursor, key, value_sql, from_sql, where_sql, params=()):
    cursor.execute(
        f"""
        UPDATE auditlog_logentry le
        SET additional_data = COALESCE(le.additional_data, '{{}}'::jsonb)
            || jsonb_build_object('{key}', {value_sql})
        FROM {from_sql}
        WHERE NOT (COALESCE(le.additional_data, '{{}}'::jsonb) ? '{key}')
            AND {value_sql} IS NOT NULL
            AND {where_sql}
        """,
        params,
    )


def backfill(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    AgendaItem = apps.get_model("agenda", "AgendaItem")
    Meeting = apps.get_model("meeting", "Meeting")
    User = apps.get_model("core", "User")
    ct_ids = {
        (ct.app_label, ct.model): ct.pk
        for ct in ContentType.objects.filter(
            app_label__in={
                "meeting",
                "invites",
                "speaker",
                "poll",
                "core",
                "organisation",
            }
        )
    }
    with schema_editor.connection.cursor() as cursor:
        _set_key(
            cursor,
            "m",
            "x.meeting_id",
            f"{AgendaItem._meta.db_table} x",
            f"x.id = {_key_id('ai')}",
        )
        for app_label, model, column, parent in VIA_PARENT:
            if (ct_id := ct_ids.get((app_label, model))) is None:
                continue
            table = apps.get_model(app_label, model)._meta.db_table
            parent_table = apps.get_model(parent)._meta.db_table
            _set_key(
                cursor,
                "m",
                "p.meeting_id",
                f"{table} x JOIN {parent_table} p ON p.id = x.{column}",
                "le.content_type_id = %s AND x.id = le.object_id",
                [ct_id],
            )
        _set_key(
            cursor,
            "o",
            "x.organisation_id",
            f"{Meeting._meta.db_table} x",
            f"x.id = {_key_id('m')}",
        )
        if (ct_id := ct_ids.get(("core", "user"))) is not None:
            _set_key(
                cursor,
                "o",
                "x.organisation_id",
                f"{User._meta.db_table} x",
                "le.content_type_id = %s AND x.id = le.object_id",
                [ct_id],
            )
        if (ct_id := ct_ids.get(("organisation", "organisation"))) is not None:
            cursor.execute(
                """
                UPDATE auditlog_logentry
                SET additional_data = COALESCE(additional_data, '{}'::jsonb)
                    || jsonb_build_object('o', object_id)
                WHERE content_type_id = %s AND object_id IS NOT NULL
                """,
                [ct_id],
            )
        # The object or its meeting is gone, the actor's organisation is the
        # best guess left. It's what the stats job used before.
        _set_key(
            cursor,
            "o",
            "x.organisation_id",
            f"{User._meta.db_table} x",
            "x.id = le.actor_id",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("stats", "0001_initial"),
        ("auditlog", "0017_add_actor_email"),
        ("agenda", "0009_remove_agendaitem_related_modified"),
        ("core", "0007_user_anonymised"),
        ("invites", "0016_alter_meetinginvite_used_by"),
        ("meeting", "0031_alter_groupmembership_user"),
        ("poll", "0017_remove_poll_initial_electoral_register_and_more"),
        ("speaker", "0019_alter_speakerlistsystem_room"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
