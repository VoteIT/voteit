from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.timezone import now
from django_fsm import FSMField, transition
from django.utils.translation import gettext_lazy as _

from voteit.agenda.permissions import AgendaPermissions
from voteit.agenda.workflows import AgendaItemWf
from voteit.core.abcs import AgendaItemContext
from voteit.core.abcs import MeetingContext
from voteit.core.fields import RichTextField
from voteit.core.models import BaseContent
from voteit.core.permissions import NOT_ALLOWED
from voteit.core.utils import relaxed_clean_html
from voteit.meeting.models import Meeting
from voteit.meeting.workflows import MeetingWf
from voteit.poll.workflows import PollWf


__all__ = ("AgendaItem", "LastRead")


class AgendaItem(BaseContent, MeetingContext, AgendaItemContext):
    name: str = "agenda_item"
    body: str = RichTextField(blank=True, default="", html_cleaner=relaxed_clean_html)
    title: str = models.CharField(max_length=100)
    state: str = FSMField(
        default=AgendaItemWf.initial,
        choices=AgendaItemWf.choices(),
        editable=False,
    )
    meeting: Meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="agenda_items"
    )
    block_discussion: bool = models.BooleanField(
        verbose_name=_("Block new discussion posts"), default=False
    )
    block_proposals: bool = models.BooleanField(
        verbose_name=_("Block new proposals"), default=False
    )
    order: int = models.PositiveSmallIntegerField(default=0)
    related_modified: Optional[datetime] = models.DateTimeField(
        editable=False, null=True, blank=True
    )

    @property
    def agenda_item(self) -> AgendaItem:
        """AgendaItemContext demands this."""
        return self

    class Meta:
        ordering = (
            "meeting",
            "order",
        )

    exporters = {"meeting": {}}
    importers = {
        "meeting": {},
        "organisation": {"remap_relations": {"user": {"last_modified_by", "author"}}},
    }

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

    def maybe_mark_related_modified(self):
        """This is a "poor man's" avoid duplicate pushes."""
        if self.state != AgendaItemWf.ARCHIVED:
            really_now = now()
            # Check if we really need to touch the database
            if (
                self.related_modified is not None
                and self.related_modified + timedelta(seconds=3) < really_now
            ) or (
                self.related_modified is None
                and (self.proposals.exists() or self.discussions.exists())
            ):
                self.related_modified = really_now
                self.save()
                return really_now

    def revert_to_last_related_modified(self):
        """
        In case something's deleted that was contained by this agenda item,
        set related_modified to the highest reasonable value.
        No need to notify users that content was changed if it's just missing.
        """
        if self.state != AgendaItemWf.ARCHIVED:
            candidates = [
                x.modified
                for x in [
                    self.proposals.order_by("-modified").first(),
                    self.discussions.order_by("-modified").first(),
                ]
                if x is not None
            ]
            if candidates:
                latest = sorted(candidates, reverse=True)[0]
                if self.related_modified != latest:
                    self.related_modified = latest
                    self.save()
                    return latest
            elif self.related_modified is not None:
                # Blank out related_modified since last entry was deleted
                self.related_modified = None
                self.save()

    def guard_no_ongoing_polls(self) -> bool:
        return not self.polls.filter(state=PollWf.ONGOING).exists()

    def guard_meeting_ongoing(self) -> bool:
        return self.meeting.state == MeetingWf.ONGOING

    @transition(
        field=state,
        target=AgendaItemWf.UPCOMING,
        source=[AgendaItemWf.PRIVATE, AgendaItemWf.CLOSED, AgendaItemWf.ONGOING],
        permission=AgendaPermissions.CHANGE,
        custom={"title": _("Make upcoming")},
        conditions=[guard_no_ongoing_polls],
    )
    def upcoming(self):
        """
        Make agenda item upcoming
        """
        pass

    @transition(
        field=state,
        source=[
            AgendaItemWf.PRIVATE,
            AgendaItemWf.UPCOMING,
            AgendaItemWf.CLOSED,
            AgendaItemWf.ONGOING,
        ],
        target=AgendaItemWf.PRIVATE,
        permission=AgendaPermissions.CHANGE,
        custom={"title": _("Unpublish")},
        conditions=[guard_no_ongoing_polls],
    )
    def unpublish(self):
        """
        Make agenda item private
        """
        pass

    @transition(
        field=state,
        source=[AgendaItemWf.PRIVATE, AgendaItemWf.UPCOMING, AgendaItemWf.CLOSED],
        target=AgendaItemWf.ONGOING,
        permission=AgendaPermissions.CHANGE,
        conditions=[guard_meeting_ongoing],
        custom={"title": _("Make ongoing")},
    )
    def ongoing(self):
        """Make agenda item ongoing"""
        pass

    @transition(
        field=state,
        target=AgendaItemWf.CLOSED,
        source=[AgendaItemWf.PRIVATE, AgendaItemWf.UPCOMING, AgendaItemWf.ONGOING],
        permission=AgendaPermissions.CHANGE,
        conditions=[guard_no_ongoing_polls],
        custom={"title": _("Close")},
    )
    def close(self):
        """
        Close agenda item
        """
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

    def mark_read(self, user: AbstractUser) -> datetime:
        last_read, created = self.last_read_set.get_or_create(user=user)
        last_read: LastRead
        if not created:
            last_read.timestamp = now()
            last_read.save()
        return last_read.timestamp

    # Annotations
    objects: models.Manager
    proposals: models.QuerySet
    polls: models.QuerySet
    discussions: models.QuerySet
    last_read_set: models.QuerySet
    text_documents: models.QuerySet
    text_paragraphs: models.QuerySet


class LastRead(AgendaItemContext, MeetingContext):
    """
    Tracks last time a user read an agenda item.
    Frontend checks modified against timestamp to see if there are any new posts.
    """

    agenda_item: AgendaItem = models.ForeignKey(
        AgendaItem,
        on_delete=models.CASCADE,
        related_name="last_read_set",
    )
    meeting: Meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="last_read_set",
    )
    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="last_read_set",
    )
    timestamp: datetime = models.DateTimeField(auto_now_add=True)

    def save(self, **kwargs):
        if self.pk is None:  # created
            self.meeting = self.agenda_item.meeting
        super().save(**kwargs)

    # Annotations
    objects: models.Manager
