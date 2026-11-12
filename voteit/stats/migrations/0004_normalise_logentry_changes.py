"""
Rewrite old auditlog changes into the format current entries have, so stats and
archive_auditlog can read them.

Until late 2024 auditlog stored related objects by str(), e.g. a user as
"Jane Doe (jane) 12" and a meeting by its title. Those become pk strings where
the object can still be identified. Others, mostly deleted users, are left as
they are. Role values come in several formats, some with full role names, and
all become a sorted list of role codes. A few entries hold a meeting title in
additional_data["m"].
"""

import ast
import re

from django.db import migrations
from django.db.models import Q

BATCH = 2000

ROLE_KEYS = ("assigned", "roles")
# key -> additional_data key holding the same object
CONTEXT_KEYS = {"meeting": "m", "organisation": "o", "agenda_item": "ai"}
# "context" points to different models
CONTEXT_OF = {
    "meetingroles": "m",
    "organisationroles": "o",
}
FK_KEYS = (
    "agenda_item",
    "context",
    "meeting",
    "meeting_group",
    "organisation",
    "user",
)

# Role names before the meeting roles got short codes
LEGACY_ROLES = {
    "discusser": "di",
    "moderator": "mo",
    "participant": "pa",
    "potential_voter": "pv",
    "proposer": "pr",
}

_ROLE_LABEL_RE = re.compile(r"\(([\w-]+)\)")
# "Jane Doe (jane) 12": userid and organisation
_USER_RE = re.compile(r"\(([^()]*)\) (\d+)$")
# "[username] 12"
_USERNAME_RE = re.compile(r"^\[(.*)\] \d+$")
_SLS_RE = re.compile(r"^SLS (\d+)$")


def normalise_roles(value):
    """
    >>> normalise_roles("('discusser', 'moderator', 'participant')")
    "['di', 'mo', 'pa']"
    >>> normalise_roles("{Moderator (mo), Participant (pa)}")
    "['mo', 'pa']"
    >>> normalise_roles("{'pa', 'di'}"), normalise_roles("['pr', 'pv', 'di']")
    ("['di', 'pa']", "['di', 'pr', 'pv']")
    >>> normalise_roles("('org_manager',)"), normalise_roles("['proposer', 'potential_voter']")
    ("['org_manager']", "['pr', 'pv']")
    >>> [normalise_roles(v) for v in ("", "()", "[]", "set()", "None", None)]
    ['[]', '[]', '[]', '[]', 'None', None]
    """
    if value is None or value == "None":
        return value
    if value in ("", "set()"):
        codes = []
    elif found := _ROLE_LABEL_RE.findall(value):
        codes = found
    else:
        try:
            codes = list(ast.literal_eval(value))
        except (ValueError, SyntaxError, TypeError):
            return value
    return str(sorted({LEGACY_ROLES.get(c, c) for c in codes}))


def _int(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


class Lookups:
    def __init__(self, apps):
        self.apps = apps
        User = apps.get_model("core", "User")
        self.userids = {}
        self.usernames = {}
        for pk, userid, org_id, username in User.objects.values_list(
            "pk", "userid", "organisation_id", "username"
        ):
            if userid:
                self.userids[(userid, org_id)] = pk
            self.usernames[username] = pk
        self.by_title = {
            "agenda_item": self._unique(
                apps.get_model("agenda", "AgendaItem"), "title"
            ),
            "meeting_group": self._unique(
                apps.get_model("meeting", "MeetingGroup"), "title", "groupid"
            ),
        }
        self.speaker_systems = self._unique(
            apps.get_model("speaker", "SpeakerListSystem"), "room__title"
        )
        self.meetings = self._unique(
            apps.get_model("meeting", "Meeting"), "title", meeting="organisation_id"
        )
        self.fk_cache = {}

    @staticmethod
    def _unique(model, *fields, meeting="meeting_id"):
        """{(meeting_id, value): pk} for values that identify one object."""
        found = {}
        for field in fields:
            for row in model.objects.values_list(meeting, field, "pk"):
                if row[1] is None:
                    continue
                key = (row[0], row[1][:30] if field == "room__title" else row[1])
                found[key] = None if key in found and found[key] != row[2] else row[2]
        return {k: v for k, v in found.items() if v is not None}

    def user(self, value):
        if match := _USER_RE.search(value):
            return self.userids.get((match[1], int(match[2])))
        if match := _USERNAME_RE.match(value):
            return self.usernames.get(match[1])

    def current_fk(self, ct, key, object_id):
        """FK value of the logged object, if it still exists."""
        cache_key = (ct.pk, key)
        if cache_key not in self.fk_cache:
            try:
                model = self.apps.get_model(ct.app_label, ct.model)
                field = model._meta.get_field(key)
            except LookupError:
                field = None
            if field is None or not field.many_to_one:
                self.fk_cache[cache_key] = None
            else:
                self.fk_cache[cache_key] = (model, field.attname)
        if (found := self.fk_cache[cache_key]) is None:
            return None
        model, attname = found
        return (
            model.objects.filter(pk=object_id)
            .values_list(attname, flat=True)
            .first()
        )

    def by_meeting(self, ct, key, meeting_id, value):
        if key in self.by_title:
            return self.by_title[key].get((meeting_id, value))
        if ct.model == "speakersystemroles" and key == "context":
            if match := _SLS_RE.match(value):
                return int(match[1])
            return self.speaker_systems.get((meeting_id, value))


def resolve(lookups, ct, entry, key, side, value):
    if key == "user" and (found := lookups.user(value)) is not None:
        return found
    extra = entry.additional_data or {}
    # additional_data describes the object as it was saved, or before delete.
    current_side = 0 if entry.action == 2 else 1
    if side == current_side:
        context_key = CONTEXT_OF.get(ct.model) if key == "context" else None
        context_key = context_key or CONTEXT_KEYS.get(key)
        if context_key and (found := _int(extra.get(context_key))) is not None:
            return found
        if entry.object_id is not None and (
            found := lookups.current_fk(ct, key, entry.object_id)
        ):
            return found
    return lookups.by_meeting(ct, key, _int(extra.get("m")), value)


def normalise_entry(lookups, ct, entry) -> bool:
    changed = False
    changes = entry.changes or {}
    for key, values in changes.items():
        if not isinstance(values, list):
            continue
        if key in ROLE_KEYS:
            new = [normalise_roles(v) for v in values]
        elif key in FK_KEYS:
            new = []
            for side, value in enumerate(values):
                if isinstance(value, str) and value != "None" and not value.isdigit():
                    if (found := resolve(lookups, ct, entry, key, side, value)) is not None:
                        value = str(found)
                new.append(value)
        else:
            continue
        if new != values:
            changes[key] = new
            changed = True
    extra = entry.additional_data or {}
    if isinstance(extra.get("m"), str):
        meeting_id = _int(extra["m"]) or lookups.meetings.get(
            (_int(extra.get("o")), extra["m"])
        )
        if meeting_id is None:
            del extra["m"]
        else:
            extra["m"] = meeting_id
        changed = True
    return changed


def normalise(apps, schema_editor):
    LogEntry = apps.get_model("auditlog", "LogEntry")
    ContentType = apps.get_model("contenttypes", "ContentType")
    cts = ContentType.objects.in_bulk()
    lookups = Lookups(apps)
    qs = LogEntry.objects.filter(
        Q(changes__has_any_keys=[*FK_KEYS, *ROLE_KEYS])
        | Q(additional_data__m__regex=r"[^0-9]")
    ).only("id", "action", "content_type_id", "object_id", "changes", "additional_data")
    batch = []
    for entry in qs.iterator(chunk_size=BATCH):
        if normalise_entry(lookups, cts[entry.content_type_id], entry):
            batch.append(entry)
        if len(batch) >= BATCH:
            LogEntry.objects.bulk_update(batch, ["changes", "additional_data"])
            batch = []
    if batch:
        LogEntry.objects.bulk_update(batch, ["changes", "additional_data"])


class Migration(migrations.Migration):
    dependencies = [
        ("stats", "0003_period_and_meeting_stats"),
        ("agenda", "0009_remove_agendaitem_related_modified"),
        ("core", "0007_user_anonymised"),
        ("meeting", "0031_alter_groupmembership_user"),
        ("speaker", "0019_alter_speakerlistsystem_room"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(normalise, migrations.RunPython.noop)]
