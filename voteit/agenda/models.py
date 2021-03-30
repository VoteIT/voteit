from __future__ import annotations

from django.db import models
from django_fsm import FSMField, transition
from django.utils.translation import gettext as _

from voteit.agenda.permissions import AgendaPermissions
from voteit.agenda.workflows import AgendaItemWf
from voteit.core.abcs import AgendaItemContext
from voteit.core.abcs import MeetingContext
from voteit.core.models import BaseContent
from voteit.core.permissions import NOT_ALLOWED
from voteit.meeting.models import Meeting


__all__ = ("AgendaItem",)


class AgendaItem(BaseContent, MeetingContext, AgendaItemContext):
    name = "agenda_item"
    title: str = models.CharField(max_length=100)
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

    @property
    def agenda_item(self) -> AgendaItem:
        """ AgendaItemContext demands this."""
        return self

    class Meta:
        ordering = (
            "meeting",
            "order",
        )

    def save(self, **kw):
        """Set order as last agenda item for meeting when creating."""
        if not self.pk:
            max_order = self.meeting.agenda_items.aggregate(
                max_order=models.Max("order")
            )["max_order"]
            if max_order is not None:
                self.order = max_order + 1
        super().save(**kw)

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
        """Make agenda item upcoming"""
        pass

    @transition(
        field=state,
        target=AgendaItemWf.PRIVATE,
        permission=AgendaPermissions.CHANGE,
    )
    def unpublish(self):
        """Make agenda item private"""
        pass

    @transition(
        field=state,
        target=AgendaItemWf.ONGOING,
        permission=AgendaPermissions.CHANGE,
    )
    def ongoing(self):
        """Make agenda item ongoing"""
        pass

    @transition(
        field=state,
        target=AgendaItemWf.CLOSED,
        permission=AgendaPermissions.CHANGE,
    )
    def close(self):
        """Close agenda item"""
        pass

    @transition(
        field=state,
        target=AgendaItemWf.ARCHIVED,
        source="*",
        permission=NOT_ALLOWED,  # Handled by scripts
    )
    def archive(self):
        # Mark agenda item as archived. Handled by scripts.
        # It should be able to go to archived from any state.
        pass

    @property
    def is_private(self) -> bool:
        return self.state == AgendaItemWf.PRIVATE
