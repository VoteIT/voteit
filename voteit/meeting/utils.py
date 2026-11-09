from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.db.models.functions import Collate

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
