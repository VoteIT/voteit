from django.db import models
from django_fsm import FSMField, transition
from django.utils.translation import gettext as _
from voteit.agenda.permissions import AgendaPermissions
from voteit.agenda.workflows import AgendaItemWf

from voteit.core.models import BaseContent
from voteit.meeting.models import Meeting


__all__ = 'AgendaItem',


class AgendaItem(BaseContent):
    state = FSMField(
        default=AgendaItemWf.initial,
        choices=AgendaItemWf.choices(),
        editable=False,
    )
    meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="agenda_items"
    )
    block_discussion = models.BooleanField(
        verbose_name=_("Block new discussion posts"), default=False
    )
    block_proposals = models.BooleanField(
        verbose_name=_("Block new proposals"), default=False
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
        target=AgendaItemWf.UPCOMING,
        permission=AgendaPermissions.CHANGE,
    )
    def upcoming(self):
        """ Make agenda item upcoming
        """
        pass

    @transition(
        field=state,
        target=AgendaItemWf.PRIVATE,
        permission=AgendaPermissions.CHANGE,
    )
    def unpublish(self):
        """ Make agenda item private
        """
        pass

    @transition(
        field=state,
        target=AgendaItemWf.ONGOING,
        permission=AgendaPermissions.CHANGE,
    )
    def ongoing(self):
        """ Make agenda item ongoing
        """
        pass

    @transition(
        field=state,
        target=AgendaItemWf.CLOSED,
        permission=AgendaPermissions.CHANGE,
    )
    def close(self):
        """ Close agenda item
        """
        pass

    @transition(
        field=state,
        target=AgendaItemWf.ARCHIVED,
        permission="__not_allowed__",  # Handled by scripts
    )
    def archive(self):
        # Mark agenda item as archived. Handled by scripts.
        # It should be able to go to archived from any state.
        pass
