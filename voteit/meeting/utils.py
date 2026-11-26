from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.db.models.functions import Collate
from django.utils.text import slugify

from voteit.core import PERM
from voteit.meeting.channels import broadcast_meeting
from voteit.meeting.messages import MeetingDialectChanged
from voteit.meeting.roles import ROLE_MODERATOR

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting
    from voteit.agenda.models import AgendaItem


def sort_agenda_items(
    meeting: Meeting, locale_name: str = "sv-x-icu", reorder=False
) -> models.QuerySet[AgendaItem]:
    qs = meeting.agenda_items.order_by(Collate(models.F("title"), locale_name))
    if reorder:
        for i, ai in enumerate(qs, 1):
            if ai.order != i:
                ai.order = i
                ai.save()
    return qs


def notify_dialect_changed(meeting: Meeting) -> None:
    msg = MeetingDialectChanged(payload={"pk": meeting.pk})
    broadcast_meeting(meeting.pk, msg)


def can_see_emails(user, meeting: Meeting | None = None) -> bool:
    """
    Whether user lists rendered for this user may include email addresses.

    Superusers, org managers and moderators of the meeting. Ordinary participants
    get the list without them -- see UserListSerializer.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    org = user.organisation
    if org is not None and user.has_perm(org.get_perm(PERM.MANAGE), org):
        return True
    return meeting is not None and meeting.has_roles(user, ROLE_MODERATOR)


def active_meetings_by_user(users) -> dict[int, list[dict]]:
    """
    Upcoming and ongoing meetings each user has roles in, by title, as
    ``{user_pk: [{pk, title, state}, ...]}``.
    """
    from voteit.meeting.models import MeetingRoles
    from voteit.meeting.statemachines import MeetingStateMachine

    meetings = {}
    for row in (
        MeetingRoles.objects.filter(
            user__in=users,
            context__state__in=(
                MeetingStateMachine.upcoming.value,
                MeetingStateMachine.ongoing.value,
            ),
        )
        .order_by("context__title")
        .values("user_id", "context_id", "context__title", "context__state")
    ):
        meetings.setdefault(row["user_id"], []).append(
            {
                "pk": row["context_id"],
                "title": row["context__title"],
                "state": row["context__state"],
            }
        )
    return meetings


def suggest_groupid(title: str, taken: set[str], max_length: int = 100) -> str:
    """
    Slug from title that isn't in taken. The result is added to taken, so callers
    creating several groups can reuse the same set.

    >>> taken = {"board", "board-1"}
    >>> suggest_groupid("Board", taken)
    'board-2'
    >>> "board-2" in taken
    True
    >>> suggest_groupid("Ödeshög kommun", set())
    'odeshog-kommun'
    >>> len(suggest_groupid("", set()))
    8
    >>> long = suggest_groupid("x" * 120, {"x" * 100})
    >>> len(long), long[-2:]
    (100, '-1')
    """
    from voteit.meeting.models import _rnd_role_id

    base = (slugify(title) or _rnd_role_id())[:max_length]
    groupid = base
    i = 0
    while groupid in taken:
        i += 1
        suffix = f"-{i}"
        groupid = base[: max_length - len(suffix)] + suffix
    taken.add(groupid)
    return groupid


def existing_group_identity(meeting: Meeting) -> tuple[set[str], dict[str, str]]:
    """Taken groupids, and lowercased title -> groupid, for clash checks."""
    rows = meeting.groups.values_list("groupid", "title")
    return {gid for gid, _ in rows}, {title.lower(): gid for gid, title in rows}


def find_group_title_clashes(
    title_map: dict[str, str], items: list[tuple[str, str]]
) -> list[str]:
    """
    Titles in items (groupid, title) that title_map (from existing_group_identity)
    holds under another groupid. Matching is by groupid, so the same groupid is fine.

    >>> find_group_title_clashes({"board": "b"}, [("b", "Board"), ("x", "BOARD")])
    ['BOARD']
    """
    clashes = []
    for groupid, title in items:
        existing = title_map.get(title.lower())
        if existing is not None and existing != groupid:
            clashes.append(title)
    return clashes


def is_valid_groupid(value: str) -> bool:
    """
    >>> is_valid_groupid("hello-world")
    True
    >>> is_valid_groupid("Hello World")
    False
    """
    return bool(value) and value == slugify(value)
