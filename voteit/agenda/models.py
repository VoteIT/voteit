from django.db import models
from django_fsm import FSMField, transition
from voteit.agenda.permissions import AgendaPermissions
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

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        """ Set order as last agenda item for meeting when creating.
        """
        if not self.pk:
            max_order = self.meeting.agenda_items.aggregate(max_order=models.Max('order'))['max_order']
            if max_order is not None:
                self.order = max_order + 1
        super().save(force_insert, force_update, using, update_fields)

    def get_proposals(self):
        return self.proposals.all()

    def get_polls(self):
        return self.polls.all()

    def get_discussions(self):
        return self.discussions.all()

    @transition(
        field=state,
        source=[AgendaItemWf.PRIVATE, AgendaItemWf.ONGOING],
        target=AgendaItemWf.UPCOMING,
        permission=AgendaPermissions.CHANGE,
    )
    def upcoming(self):
        """ Make agenda item upcoming
        """
        pass

    @transition(
        field=state,
        source=[AgendaItemWf.UPCOMING],
        target=AgendaItemWf.PRIVATE,
        permission=AgendaPermissions.CHANGE,
    )
    def unpublish(self):
        """ Make agenda item private
        """
        pass

    @transition(
        field=state,
        source=[AgendaItemWf.UPCOMING, AgendaItemWf.CLOSED],
        target=AgendaItemWf.ONGOING,
        permission=AgendaPermissions.CHANGE,
    )
    def open(self):
        """ Make agenda item ongoing
        """
        pass

    @transition(
        field=state,
        source=[AgendaItemWf.ONGOING],
        target=AgendaItemWf.CLOSED,
        permission=AgendaPermissions.CHANGE,
    )
    def close(self):
        """ Close agenda item
        """
        pass
