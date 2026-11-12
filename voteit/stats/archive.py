"""
Aggregate, archive and delete old auditlog entries, one calendar month at a time.
Run through ``manage.py archive_auditlog``.
"""

from __future__ import annotations

import ast
import gzip
import json
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC
from datetime import date
from datetime import datetime
from typing import TYPE_CHECKING

from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files import File
from django.core.files.storage import storages
from django.db import models
from django.db import transaction
from django.db.models.functions import TruncMonth
from django.utils import timezone
from voteit.messaging.models import Connection

from voteit.stats.models import MeetingStats
from voteit.stats.models import OrganisationPeriodStats

if TYPE_CHECKING:
    from django.core.files.storage import Storage

STORAGE_ALIAS = "auditlog_archive"

# Kept as [old, new] from LogEntry.changes. Never free text or names.
FK_KEYS = frozenset(
    {
        "agenda_item",
        "context",
        "meeting",
        "meeting_group",
        "organisation",
        "poll",
        "room",
        "speaker_system",
        "user",
    }
)
ROLE_KEYS = frozenset({"assigned", "roles"})
BOOL_KEYS = frozenset({"enabled"})
RAW_KEYS = frozenset({"state"})
ARCHIVED_CHANGE_KEYS = FK_KEYS | ROLE_KEYS | BOOL_KEYS | RAW_KEYS | {"last_login"}

# Not the choice labels, those are translated.
ACTION_NAMES = {
    LogEntry.Action.CREATE: "create",
    LogEntry.Action.UPDATE: "update",
    LogEntry.Action.DELETE: "delete",
    LogEntry.Action.ACCESS: "access",
}
PARTICIPANT = "pa"

# auditlog renders roles as "{Moderator (mo), Participant (pa)}"
_ROLE_RE = re.compile(r"\(([\w-]+)\)")


def parse_int(value) -> int | None:
    """
    >>> parse_int("12"), parse_int(12), parse_int("None"), parse_int(None), parse_int("A title")
    (12, 12, None, None, None)
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def parse_roles(value) -> list[str] | None:
    """
    Auditlog renders roles in several ways. Migration stats 0004 turned older
    entries into the list form.

    >>> parse_roles("{Moderator (mo), Participant (pa)}")
    ['mo', 'pa']
    >>> parse_roles("['pa', 'di']"), parse_roles("{'pa', 'di'}")
    (['di', 'pa'], ['di', 'pa'])
    >>> parse_roles("[]"), parse_roles(""), parse_roles("set()"), parse_roles("None")
    ([], [], [], None)
    """
    if value is None or value == "None":
        return None
    if value in ("", "set()"):
        return []
    if found := _ROLE_RE.findall(value):
        return sorted(found)
    try:
        return sorted(ast.literal_eval(value))
    except (ValueError, SyntaxError, TypeError):
        return None


def _parse_bool(value) -> bool | None:
    return {"True": True, "False": False}.get(value)


def extract_facts(changes: dict | None) -> dict:
    """
    The whitelisted part of a log entry's changes.

    >>> extract_facts({"user": ["None", "5"], "assigned": ["[]", "{Participant (pa)}"],
    ...     "first_name": ["", "Jane"]})
    {'assigned': [[], ['pa']], 'user': [None, 5]}
    >>> extract_facts({"last_login": ["2026-01-01 10:00", "2026-01-02 10:00"]})
    {'last_login': True}
    >>> extract_facts({"state": ["published", "approved"], "enabled": ["False", "True"]})
    {'enabled': [False, True], 'state': ['published', 'approved']}
    >>> extract_facts(None)
    {}
    """
    facts = {}
    for key, values in sorted((changes or {}).items()):
        if key not in ARCHIVED_CHANGE_KEYS:
            continue
        if key == "last_login":
            facts[key] = True
        elif key in FK_KEYS:
            facts[key] = [parse_int(v) for v in values]
        elif key in ROLE_KEYS:
            facts[key] = [parse_roles(v) for v in values]
        elif key in BOOL_KEYS:
            facts[key] = [_parse_bool(v) for v in values]
        else:
            facts[key] = list(values)
    return facts


def entry_to_record(entry: dict) -> dict:
    """
    Turn a LogEntry (as a dict of RECORD_FIELDS) into an archive record.

    >>> entry_to_record({"id": 1, "timestamp": datetime(2024, 10, 3, 12, tzinfo=UTC),
    ...     "action": 1, "content_type__app_label": "meeting", "content_type__model": "meetingroles",
    ...     "object_id": 3, "object_pk": "3", "actor_id": 4, "cid": None,
    ...     "additional_data": {"o": 1, "m": 2}, "changes": {"assigned": ["[]", "{Participant (pa)}"]}})
    ... # doctest: +NORMALIZE_WHITESPACE
    {'id': 1, 'ts': '2024-10-03T12:00:00+00:00', 'action': 'update', 'ct': 'meeting.meetingroles',
     'obj': 3, 'actor': 4, 'o': 1, 'm': 2, 'ai': None, 'cid': None, 'facts': {'assigned': [[], ['pa']]}}
    """
    extra = entry["additional_data"] or {}
    return {
        "id": entry["id"],
        "ts": entry["timestamp"].isoformat(),
        "action": ACTION_NAMES.get(entry["action"], entry["action"]),
        "ct": f"{entry['content_type__app_label']}.{entry['content_type__model']}",
        "obj": entry["object_id"]
        if entry["object_id"] is not None
        else entry["object_pk"],
        "actor": entry["actor_id"],
        "o": parse_int(extra.get("o")),
        "m": parse_int(extra.get("m")),
        "ai": parse_int(extra.get("ai")),
        "cid": entry["cid"],
        "facts": extract_facts(entry["changes"]),
    }


RECORD_FIELDS = (
    "id",
    "timestamp",
    "action",
    "content_type__app_label",
    "content_type__model",
    "object_id",
    "object_pk",
    "actor_id",
    "cid",
    "additional_data",
    "changes",
)


# Periods ----------------------------------------------------------------------


def month_start(day: date) -> datetime:
    return datetime(day.year, day.month, 1, tzinfo=UTC)


def next_month(start: datetime) -> datetime:
    """
    >>> next_month(datetime(2024, 12, 1, tzinfo=UTC))
    datetime.datetime(2025, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
    """
    if start.month == 12:
        return start.replace(year=start.year + 1, month=1)
    return start.replace(month=start.month + 1)


def cutoff_for(months: int, now: datetime | None = None) -> datetime:
    """
    First day of the month ``months`` months back. Everything before it gets archived.

    >>> cutoff_for(18, datetime(2026, 11, 11, tzinfo=UTC))
    datetime.datetime(2025, 5, 1, 0, 0, tzinfo=datetime.timezone.utc)
    >>> cutoff_for(18, datetime(2026, 11, 30, 23, 59, tzinfo=UTC))
    datetime.datetime(2025, 5, 1, 0, 0, tzinfo=datetime.timezone.utc)
    >>> cutoff_for(0, datetime(2026, 11, 11, tzinfo=UTC))
    datetime.datetime(2026, 11, 1, 0, 0, tzinfo=datetime.timezone.utc)
    """
    now = (now or timezone.now()).astimezone(UTC)
    total = now.year * 12 + now.month - 1 - months
    return datetime(total // 12, total % 12 + 1, 1, tzinfo=UTC)


def months_before(cutoff: datetime) -> list[datetime]:
    """Months with log entries before cutoff, oldest first."""
    return list(
        LogEntry.objects.filter(timestamp__lt=cutoff)
        .annotate(month=TruncMonth("timestamp", tzinfo=UTC))
        .values_list("month", flat=True)
        .distinct()
        .order_by("month")
    )


def _range(start: datetime, end: datetime) -> dict:
    return {"timestamp__gte": start, "timestamp__lt": end}


def _ids(values) -> set[int]:
    # A few old entries hold a meeting title in "m".
    return {i for v in values if (i := parse_int(v)) is not None}


# Aggregates -------------------------------------------------------------------
# additional_data isn't indexed, so meetings are handled in batches: a filter on
# it scans the table (or every entry of a content type).


def meeting_participants(meeting_ids: set[int]) -> dict[int, set[int]]:
    """Users that held the participant role in each meeting at some point."""
    from voteit.meeting.models import MeetingRoles

    found = {m: set() for m in meeting_ids}
    if not meeting_ids:
        return found
    ct = ContentType.objects.get_for_model(MeetingRoles)
    owner: dict[int, int] = {}
    with_pa: dict[int, int] = {}
    for meeting_id, object_id, changes in LogEntry.objects.filter(
        content_type=ct, additional_data__m__in=meeting_ids
    ).values_list("additional_data__m", "object_id", "changes"):
        changes = changes or {}
        if "user" in changes:
            # Create has the user as new value, delete as old.
            old, new = (parse_int(v) for v in changes["user"])
            if user_id := new or old:
                owner[object_id] = user_id
        if any(
            PARTICIPANT in (parse_roles(v) or ()) for v in changes.get("assigned", ())
        ):
            with_pa[object_id] = meeting_id
    for object_id, meeting_id in with_pa.items():
        if object_id in owner:
            found[meeting_id].add(owner[object_id])
    for meeting_id, user_id in MeetingRoles.objects.filter(
        context_id__in=meeting_ids, assigned__contains=PARTICIPANT
    ).values_list("context_id", "user_id"):
        found[meeting_id].add(user_id)
    return found


def meeting_polls(meeting_ids: set[int]) -> dict[int, set[int]]:
    from voteit.poll.models import Poll

    found = {m: set() for m in meeting_ids}
    if not meeting_ids:
        return found
    ct = ContentType.objects.get_for_model(Poll)
    pairs = set(
        LogEntry.objects.filter(content_type=ct, additional_data__m__in=meeting_ids)
        .values_list("additional_data__m", "object_id")
        .distinct()
    )
    pairs.update(
        Poll.objects.filter(meeting_id__in=meeting_ids).values_list("meeting_id", "pk")
    )
    for meeting_id, poll_id in pairs:
        if poll_id is not None:
            found[meeting_id].add(poll_id)
    return found


def meeting_voters(polls: dict[int, set[int]]) -> dict[int, set[int]]:
    """Voters by actor of vote creation, plus current votes."""
    from voteit.poll.models import Vote

    found = {m: set() for m in polls}
    if not polls:
        return found
    meeting_of_poll = {str(p): m for m, poll_ids in polls.items() for p in poll_ids}
    # Votes on polls deleted before the "m" backfill only point out their poll.
    in_meetings = models.Q(additional_data__m__in=list(polls))
    if meeting_of_poll:
        in_meetings |= models.Q(changes__poll__1__in=list(meeting_of_poll))
    for meeting_id, poll_id, actor_id in (
        LogEntry.objects.filter(
            in_meetings,
            content_type=ContentType.objects.get_for_model(Vote),
            action=LogEntry.Action.CREATE,
            actor_id__isnull=False,
        )
        .values_list("additional_data__m", "changes__poll__1", "actor_id")
        .distinct()
    ):
        meeting_id = parse_int(meeting_id)
        if meeting_id not in found:
            meeting_id = meeting_of_poll.get(poll_id)
        if meeting_id in found:
            found[meeting_id].add(actor_id)
    # Votes were logged from late 2026 on. Cleared votes keep their row.
    for meeting_id, user_id in (
        Vote.objects.filter(poll__meeting_id__in=list(polls))
        .values_list("poll__meeting_id", "user_id")
        .distinct()
    ):
        found[meeting_id].add(user_id)
    return found


def meeting_titles(meeting_ids: set[int]) -> dict[int, str]:
    from voteit.meeting.models import Meeting

    titles = dict(Meeting.objects.filter(pk__in=meeting_ids).values_list("pk", "title"))
    if missing := meeting_ids - set(titles):
        # A deleted meeting's title is left in the log.
        for meeting_id, title in (
            LogEntry.objects.filter(
                content_type=ContentType.objects.get_for_model(Meeting),
                object_id__in=missing,
            )
            .order_by("object_id", "-timestamp")
            .distinct("object_id")
            .values_list("object_id", "object_repr")
        ):
            titles[meeting_id] = title
    return titles


def update_meeting_stats(meeting_orgs: dict[int, int]) -> int:
    """
    Computed from every remaining entry of each meeting. If earlier entries were
    already deleted, counts only go up and first_activity stays.
    """
    meeting_ids = set(meeting_orgs)
    spans = {
        parse_int(row["meeting"]): row
        for row in LogEntry.objects.filter(additional_data__m__in=meeting_ids)
        .values(meeting=models.F("additional_data__m"))
        .annotate(first=models.Min("timestamp"), last=models.Max("timestamp"))
    }
    participants = meeting_participants(meeting_ids)
    polls = meeting_polls(meeting_ids)
    voters = meeting_voters(polls)
    titles = meeting_titles(meeting_ids)
    existing = MeetingStats.objects.in_bulk(meeting_ids, field_name="meeting_id")
    for meeting_id, org_id in meeting_orgs.items():
        if (span := spans.get(meeting_id)) is None:
            continue
        title = (titles.get(meeting_id) or "")[:255]
        values = {
            "unique_participants": len(participants[meeting_id]),
            "unique_voters": len(voters[meeting_id]),
            "poll_count": len(polls[meeting_id]),
        }
        if (stats := existing.get(meeting_id)) is None:
            MeetingStats.objects.create(
                meeting_id=meeting_id,
                org_id=org_id,
                title=title,
                first_activity=span["first"],
                last_activity=span["last"],
                **values,
            )
            continue
        # Earlier entries were archived and deleted when the first one is gone.
        complete = span["first"] <= stats.first_activity
        for key, value in values.items():
            setattr(stats, key, value if complete else max(getattr(stats, key), value))
        stats.first_activity = min(stats.first_activity, span["first"])
        stats.last_activity = max(stats.last_activity, span["last"])
        stats.title = title or stats.title
        stats.save()
    return len(meeting_orgs)


def period_stats_values(org_id: int, start: datetime, end: datetime) -> dict:
    User = get_user_model()
    entries = LogEntry.objects.filter(additional_data__o=org_id, **_range(start, end))
    meeting_ids = _ids(
        entries.filter(additional_data__has_key="m")
        .values_list("additional_data__m", flat=True)
        .distinct()
    )
    participants = set().union(*meeting_participants(meeting_ids).values())
    return dict(
        unique_online_users=Connection.objects.filter(
            user_id__in=User.objects.filter(organisation_id=org_id).values("pk"),
            connected_at__gte=start,
            connected_at__lt=end,
        )
        .values("user_id")
        .distinct()
        .count(),
        # The logged object is the user, the actor is usually missing.
        unique_logins=entries.filter(
            content_type=ContentType.objects.get_for_model(User),
            action=LogEntry.Action.UPDATE,
            changes__has_key="last_login",
        )
        .values("object_id")
        .distinct()
        .count(),
        unique_actors=entries.filter(actor_id__isnull=False)
        .values("actor_id")
        .distinct()
        .count(),
        active_meetings=len(meeting_ids),
        unique_participants=len(participants),
    )


def save_period_stats(
    org_id: int, period: str, start: datetime, end: datetime, *, refresh: bool
) -> bool:
    """Create the row, or recompute an existing one with refresh. True if saved."""
    lookup = {"org_id": org_id, "period": period, "start": start.date()}
    exists = OrganisationPeriodStats.objects.filter(**lookup).exists()
    if exists and not refresh:
        return False
    values = period_stats_values(org_id, start, end)
    if exists:
        OrganisationPeriodStats.objects.filter(**lookup).update(**values)
    else:
        OrganisationPeriodStats.objects.create(**lookup, **values)
    return True


def year_complete(year_start: datetime, start: datetime, storage: Storage) -> bool:
    """
    No month of the year before start was archived and deleted. False when
    earlier months still have entries too, the year was handled on the first.
    """
    if LogEntry.objects.filter(**_range(year_start, start)).exists():
        return False
    month = year_start
    while month < start:
        if storage.exists(archive_filename(month)):
            return False
        month = next_month(month)
    return True


@dataclass
class MonthResult:
    month: datetime
    entries: int = 0
    org_months: int = 0
    org_years: int = 0
    meetings: int = 0
    deleted: int = 0
    filename: str = ""


def aggregate_month(
    start: datetime, result: MonthResult, *, storage: Storage, refresh: bool = False
):
    """
    Period rows are written once. With refresh, existing ones are recomputed
    when all their entries are still there.
    """
    from voteit.organisation.models import Organisation

    end = next_month(start)
    entries = LogEntry.objects.filter(**_range(start, end))
    org_ids = set(
        Organisation.objects.filter(
            pk__in=_ids(
                entries.filter(additional_data__has_key="o")
                .values_list("additional_data__o", flat=True)
                .distinct()
            )
        ).values_list("pk", flat=True)
    )
    year_start = start.replace(month=1)
    year_end = year_start.replace(year=year_start.year + 1)
    # The rest of a year that isn't over yet is still to come.
    year_done = year_end <= timezone.now()
    refresh_year = refresh and year_done and year_complete(year_start, start, storage)
    for org_id in sorted(org_ids):
        # Months are deleted whole, so one with entries is complete.
        if save_period_stats(
            org_id, OrganisationPeriodStats.MONTH, start, end, refresh=refresh
        ):
            result.org_months += 1
        # Created while archiving the year's first remaining month, so the
        # rest of the year is still there.
        if year_done and save_period_stats(
            org_id,
            OrganisationPeriodStats.YEAR,
            year_start,
            year_end,
            refresh=refresh_year,
        ):
            result.org_years += 1
    meeting_orgs = {}
    for m, o in (
        entries.filter(additional_data__has_key="m")
        .values_list("additional_data__m", "additional_data__o")
        .distinct()
    ):
        meeting_id, org_id = parse_int(m), parse_int(o)
        if meeting_id is not None and org_id in org_ids:
            meeting_orgs[meeting_id] = org_id
    result.meetings = update_meeting_stats(meeting_orgs)


# Archive ----------------------------------------------------------------------


def archive_filename(start: datetime) -> str:
    return f"auditlog/{start:%Y-%m}.jsonl.gz"


def write_archive(start: datetime, storage: Storage) -> tuple[str, int, int | None]:
    """Write the month's entries to storage. Returns filename, count and highest id."""
    end = next_month(start)
    name = archive_filename(start)
    count = 0
    max_id = None
    with tempfile.TemporaryFile() as fh:
        with gzip.GzipFile(fileobj=fh, mode="wb") as gz:
            for entry in (
                LogEntry.objects.filter(**_range(start, end))
                .order_by("id")
                .values(*RECORD_FIELDS)
                .iterator(chunk_size=2000)
            ):
                gz.write(
                    json.dumps(entry_to_record(entry), separators=(",", ":")).encode()
                )
                gz.write(b"\n")
                count += 1
                max_id = entry["id"]
        fh.seek(0)
        # A rerun after a failed delete replaces the earlier file.
        if storage.exists(name):
            storage.delete(name)
        saved = storage.save(name, File(fh, name=name))
    if saved != name:  # pragma: no cover
        raise RuntimeError(f"Archive saved as {saved}, expected {name}")
    return name, count, max_id


def archive_month(
    start: datetime,
    *,
    dry_run: bool = False,
    keep_entries: bool = False,
    storage: Storage | None = None,
) -> MonthResult:
    """
    Aggregate, archive and delete one calendar month of log entries.
    keep_entries skips the delete and recomputes existing stats, so it can be rerun.
    """
    end = next_month(start)
    result = MonthResult(month=start)
    result.entries = LogEntry.objects.filter(**_range(start, end)).count()
    if dry_run or not result.entries:
        return result
    if storage is None:
        storage = storages[STORAGE_ALIAS]
    with transaction.atomic():
        aggregate_month(start, result, storage=storage, refresh=keep_entries)
    result.filename, exported, max_id = write_archive(start, storage)
    if keep_entries:
        return result
    with transaction.atomic():
        deleted, _ = LogEntry.objects.filter(
            id__lte=max_id, **_range(start, end)
        ).delete()
        if deleted != exported:
            raise RuntimeError(
                f"{start:%Y-%m}: exported {exported} entries but would delete {deleted}"
            )
    result.deleted = deleted
    return result
