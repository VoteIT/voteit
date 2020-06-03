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
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = 'meeting', 'order',

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
        """ Make agenda item upcoming. Set as last item if publishing and order not previously set.
        """
        # TODO: Order should be set on object creation, not here
        if self.state == AgendaItemWf.PRIVATE and self.order == 0:
            max_order = max(ai.order for ai in AgendaItem.objects.filter(meeting=self.meeting))
            self.order = max_order + 1

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
