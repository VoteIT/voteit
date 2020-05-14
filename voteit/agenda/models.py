from django.db import models
from django_fsm import FSMField
from voteit.agenda.workflows import AgendaItemWf

from voteit.core.models import BaseContent
from voteit.meeting.models import Meeting


class AgendaItem(BaseContent):
    state = FSMField(
        default=AgendaItemWf.initial, choices=AgendaItemWf.choices(), protected=True, editable=False,
    )
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="agenda_items")
