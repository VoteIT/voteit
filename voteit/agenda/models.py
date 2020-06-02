from django.db import models
from django_fsm import FSMField, transition
from voteit.agenda.workflows import AgendaItemWf

from voteit.core.models import BaseContent
from voteit.meeting.models import Meeting


class AgendaItem(BaseContent):
    state = FSMField(
        default=AgendaItemWf.initial,
        choices=AgendaItemWf.choices(),
        protected=True,
        editable=False,
    )
    meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="agenda_items"
    )

    def get_proposals(self):
        return self.proposals.all()

    def get_polls(self):
        return self.polls.all()

    def get_discussions(self):
        return self.discussions.all()

    @transition(
        field=state,
        source=[AgendaItemWf.PRIVATE, AgendaItemWf.ONGOING],
        target=AgendaItemWf.UPCOMING
    )
    def upcoming(self):
        """ Make agenda item upcoming
        """
        pass

    @transition(
        field=state,
        source=[AgendaItemWf.UPCOMING],
        target=AgendaItemWf.PRIVATE
    )
    def unpublish(self):
        """ Make agenda item private
        """
        pass

    @transition(
        field=state,
        source=[AgendaItemWf.UPCOMING, AgendaItemWf.CLOSED],
        target=AgendaItemWf.ONGOING
    )
    def open(self):
        """ Make agenda item ongoing
        """
        pass

    @transition(
        field=state,
        source=[AgendaItemWf.ONGOING],
        target=AgendaItemWf.CLOSED
    )
    def close(self):
        """ Close agenda item
        """
        pass
