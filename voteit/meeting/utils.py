from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.db.models.functions import Collate


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
