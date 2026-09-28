from __future__ import annotations

from datetime import datetime

from auditlog.registry import auditlog
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Max
from django.db.models import OuterRef
from django.db.models import Subquery
from django.db.models.functions import Greatest
from django.utils.timezone import now
from voteit.core.statemachines import StateMachineModelMixin

from voteit.agenda.statemachines import AgendaItemStateMachine
from voteit.core.abcs import AgendaItemContext
from voteit.core.abcs import MeetingContext
from voteit.core.fields import RichTextField
from voteit.core.models import BaseContent
from voteit.core.utils import relaxed_clean_html
from voteit.meeting.models import Meeting

__all__ = ("AgendaItem", "LastRead")

from voteit.stats.registry import history_log


def _latest_created(model: type[models.Model]) -> Subquery:
    return Subquery(
        model._base_manager.filter(agenda_item=OuterRef("pk"))
        .order_by()
        .values("agenda_item")
        .annotate(latest=Max("created"))
        .values("latest")
    )


class AgendaItemQuerySet(models.QuerySet):
    def with_related_modified(self):
        """Annotate ``related_modified``: when the newest proposal or discussion post was created."""
        from voteit.discussion.models import DiscussionPost
        from voteit.proposal.models import Proposal

        # Postgres GREATEST skips NULLs, so one kind of content is enough
        return self.annotate(
            related_modified=Greatest(
                _latest_created(Proposal), _latest_created(DiscussionPost)
            )
        )


@history_log("meeting__organisation")
@auditlog.register(
    include_fields=[
        "state",
        "title",
        "meeting",
        "body",
        "block_discussion",
        "block_proposals",
        "tags",
    ],
)
class AgendaItem(
    BaseContent, MeetingContext, AgendaItemContext, StateMachineModelMixin
):
    """
    A structured discussion/voting point within a meeting.

    Agenda items are the containers that hold proposals, polls, and discussion posts.
    Lifecycle (``AgendaItemStateMachine``): ``private → upcoming → ongoing → closed → archived``.
    State combinations with the parent meeting are documented in ``docs/workflows.md``.

    ``order`` is auto-assigned as the next sequential value for the meeting.
    ``related_modified`` isn't stored, see ``AgendaItemQuerySet.with_related_modified``.
    The frontend compares it against ``LastRead.timestamp`` to show "unread" indicators.

    ``block_discussion`` and ``block_proposals`` are moderator flags that can disable
    new content without changing the item's state.
    """

    name: str = "agenda_item"
    state_machine_name = "voteit.agenda.statemachines.AgendaItemStateMachine"
    sm: AgendaItemStateMachine
    body: str = RichTextField(blank=True, default="", html_cleaner=relaxed_clean_html)
    title: str = models.CharField(max_length=100)
    state: str = models.CharField(
        default=AgendaItemStateMachine.initial_state.value,
        choices=[(s.value, str(s.name)) for s in AgendaItemStateMachine.states],
        max_length=20,
    )
    meeting: Meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="agenda_items"
    )
    block_discussion: bool = models.BooleanField(
        verbose_name="Block new discussion posts", default=False
    )
    block_proposals: bool = models.BooleanField(
        verbose_name="Block new proposals", default=False
    )
    order: int = models.PositiveSmallIntegerField(default=0)

    @property
    def agenda_item(self) -> AgendaItem:
        """AgendaItemContext demands this."""
        return self

    class Meta:
        ordering = (
            "meeting",
            "order",
        )

    def save(self, **kw):
        """Set order as last agenda item for meeting when creating."""
        if self.pk is None and self.order in (0, None):
            max_order = AgendaItem.objects.filter(meeting_id=self.meeting_id).aggregate(
                max_order=models.Max("order")
            )["max_order"]
            self.order = (max_order or 0) + 1
        super().save(**kw)

    def get_proposals(self):
        return self.proposals.all()

    def get_polls(self):
        return self.polls.all()

    def get_discussions(self):
        return self.discussions.all()

    def get_related_modified(self) -> datetime | None:
        """Use the annotation if the queryset had one, otherwise query for it."""
        if "related_modified" in self.__dict__:
            return self.related_modified
        if self.pk is None:
            return None
        return (
            AgendaItem.objects.filter(pk=self.pk)
            .with_related_modified()
            .values_list("related_modified", flat=True)
            .first()
        )

    def make_upcoming(self, user):
        self.sm.send("make_upcoming", user=user)

    def unpublish(self, user):
        self.sm.send("unpublish", user=user)

    def make_ongoing(self, user):
        self.sm.send("make_ongoing", user=user)

    def close(self, user):
        self.sm.send("close", user=user)

    def archive(self):
        self.state = AgendaItemStateMachine.archived.value

    @property
    def is_private(self) -> bool:
        return self.state == AgendaItemStateMachine.private.value

    @property
    def is_ongoing(self) -> bool:
        return self.state == AgendaItemStateMachine.ongoing.value

    def mark_read(self, user: AbstractUser) -> LastRead:
        last_read, _ = self.last_read_set.update_or_create(
            user=user, defaults={"timestamp": now()}
        )
        return last_read

    objects = AgendaItemQuerySet.as_manager()

    # Annotations
    meeting_id: int
    proposals: models.QuerySet
    polls: models.QuerySet
    discussions: models.QuerySet
    last_read_set: models.QuerySet
    text_documents: models.QuerySet
    text_paragraphs: models.QuerySet
    speaker_lists: models.QuerySet


class LastRead(AgendaItemContext, MeetingContext):
    """
    Tracks last time a user read an agenda item.
    Frontend checks modified against timestamp to see if there are any new posts.
    """

    name = "last_read"
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
    timestamp: datetime = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["agenda_item", "meeting", "user"],
                name="unique_last_read_combination",
            ),
        )

    def save(self, **kwargs):
        if self.pk is None:  # created
            self.meeting = self.agenda_item.meeting
        super().save(**kwargs)

    # Annotations
    objects: models.Manager
