from __future__ import annotations

from datetime import datetime
from logging import getLogger
from random import sample
from string import ascii_lowercase
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.db import transaction
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField
from django_fsm import transition
from model_utils.managers import InheritanceManager

from voteit.core.abcs import AgendaItemContext
from voteit.core.abcs import MeetingContext
from voteit.core.models import BaseContent
from voteit.proposal.permissions import ProposalPermissions
from voteit.proposal.workflows import ProposalWf
from voteit.reactions.mixins import Reactable

if TYPE_CHECKING:
    from voteit.core.models import User
    from voteit.agenda.models import AgendaItem
    from voteit.meeting.models import Meeting
    from voteit.meeting.models import MeetingGroup

__all__ = (
    "Proposal",
    "DiffProposal",
    "TextDocument",
    "TextParagraph",
)

logger = getLogger(__name__)


class Proposal(BaseContent, AgendaItemContext, MeetingContext, Reactable):
    name = "proposal"
    state: str = FSMField(default=ProposalWf.initial, choices=ProposalWf.choices())
    author: User = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        blank=True,
        null=True,
        related_name="proposals",
    )
    meeting_group: MeetingGroup = models.ForeignKey(
        "meeting.MeetingGroup",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="proposals",
    )
    prop_id: str = models.CharField(max_length=50)
    agenda_item: AgendaItem = models.ForeignKey(
        "agenda.AgendaItem",
        on_delete=models.CASCADE,
        null=True,
        related_name="proposals",
    )

    @property
    def meeting(self) -> Meeting | None:
        """While not directly related, it still good to be able to do lookups this way"""
        if self.agenda_item:
            return self.agenda_item.meeting

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["prop_id", "agenda_item"],
                name="prop_id_unique_for_ai",
            )
        ]

    exporters = {"meeting": {"meeting_kw": "agenda_item__meeting"}}
    importers = {
        "meeting": {"remap_relations": {"user": {"author"}}},
        "organisation": {
            "remap_relations": {"user": {"author", "mentions", "last_modified_by"}}
        },
    }

    @transition(
        field=state,
        source=ProposalWf.PUBLISHED,
        target=ProposalWf.RETRACTED,
        permission=ProposalPermissions.RETRACT,
        custom={"title": _("Retract")},
    )
    def retract(self):
        """Normal user operation to retract. Or for moderators."""
        pass

    @transition(
        field=state,
        source=[ProposalWf.PUBLISHED, ProposalWf.RETRACTED],
        target=ProposalWf.VOTING,
        permission=ProposalPermissions.CHANGE,
        custom={"title": _("Lock for vote")},
    )
    def lock_for_vote(self):
        """When a vote starts, mark all proposals as "voting" so they can't be retracted.
        In case a retracted proposal is part of the vote, lock that too
        since it might have been retracted very late.
        """
        pass

    @transition(
        field=state,
        source=[ProposalWf.PUBLISHED, ProposalWf.VOTING, ProposalWf.DENIED],
        target=ProposalWf.APPROVED,
        permission=ProposalPermissions.CHANGE,
        custom={"title": _("Approve")},
    )
    def approved(self):
        """Proposal approved via poll or moderator."""
        pass

    @transition(
        field=state,
        source=[ProposalWf.PUBLISHED, ProposalWf.VOTING, ProposalWf.APPROVED],
        target=ProposalWf.DENIED,
        permission=ProposalPermissions.CHANGE,
        custom={"title": _("Deny")},
    )
    def denied(self):
        """Proposal denied via poll or moderator."""
        pass

    @transition(
        field=state,
        source=ProposalWf.PUBLISHED,
        target=ProposalWf.UNHANDLED,
        permission=ProposalPermissions.CHANGE,
        custom={"title": _("Mark as unhandled")},
    )
    def unhandled(self):
        """Proposal was never handled. Automatic transition or from moderator."""
        pass

    @transition(
        field=state,
        source="+",
        target=ProposalWf.PUBLISHED,
        permission=ProposalPermissions.CHANGE,
        custom={"title": _("Publish")},
    )
    def publish(self):
        """Reset proposal back to published."""
        pass

    def save(self, **kw):
        if not self.prop_id and self.meeting is not None:
            pid_policy = self.meeting.pid_policy
            suggestion = pid_policy(self)
            if suggestion:
                self.prop_id = suggestion
            else:
                self.prop_id = _new_proposal_id(self)
        if self.prop_id not in self.tags:
            self.tags.append(self.prop_id)
        super().save(**kw)

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self}>"

    def __str__(self):
        return f"P:{self.prop_id}"

    objects = InheritanceManager()


class TextDocument(AgendaItemContext, MeetingContext):
    """
    The full text that's the basis for diff proposals.
    """

    name = "text_document"
    _should_refresh: bool = False
    title: str = models.CharField(max_length=100, default="")
    body: str = models.TextField(default="")
    base_tag: str = models.CharField(max_length=40)
    created: datetime = models.DateTimeField(editable=False, default=now)
    modified: datetime = models.DateTimeField(editable=False, auto_now=True)
    author: User = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        related_name="text_documents",
    )
    last_modified_by: User = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        related_name="text_documents_last_modified",
    )
    agenda_item: AgendaItem = models.ForeignKey(
        "agenda.AgendaItem",
        on_delete=models.CASCADE,
        related_name="text_documents",
        null=True,  # Normally no, forced in serializer
    )

    exporters = {"meeting": {"meeting_kw": "agenda_item__meeting"}}
    importers = {
        "meeting": {"remap_relations": {"user": {"author"}}},
        "organisation": {"remap_relations": {"user": {"author", "last_modified_by"}}},
    }

    @property
    def meeting(self) -> Meeting | None:
        if self.agenda_item:
            return self.agenda_item.meeting

    def create_text_paragraphs(self):
        paragraphs = get_paragraphs(self.body)
        i = 1
        for para in paragraphs:
            self.text_paragraphs.create(
                body=para, agenda_item=self.agenda_item, paragraph_id=i
            )
            i += 1
        self._should_refresh = False

    @property
    def should_refresh(self):
        return self._should_refresh

    def save(self, **kw):
        if self.pk is None:
            self._should_refresh = True
        else:
            old = TextDocument.objects.get(pk=self.pk)
            if old.body != self.body:
                self._should_refresh = True
        # We want all the subsequent creates that comes from the save signal to be within
        # the same transaction. Empty TextDocuments won't make anyone happy.
        with transaction.atomic():
            super().save(**kw)

    # Annotations
    objects: models.Manager
    text_paragraphs: models.QuerySet

    def __str__(self):
        return self.title and self.title or f"TextDoc({self.pk})"

    def __repr__(self):
        return f"TextDocument({self.pk}) {self.title[:50]}"


def get_paragraphs(text: str) -> list[str]:
    """
    Split text into paragraphs. Two linebreaks means new.
    """
    output = []
    new_para = True
    for row in text.splitlines():
        row = row.strip()
        if row:
            if new_para:
                output.append(row)
            else:
                output[-1] += "\n"
                output[-1] += row
            new_para = False
        else:
            new_para = True
    return output


class TextParagraph(AgendaItemContext, MeetingContext):
    """
    Text paragraphs are the basis for diff-text functionality.
    These are the initial text body other proposals diff against.
    """

    name = "text_paragraph"
    body: str = models.TextField(editable=False)
    created: datetime = models.DateTimeField(editable=False, default=now)
    modified: datetime = models.DateTimeField(editable=False, auto_now=True)
    paragraph_id: int = models.PositiveSmallIntegerField(default=1)
    text_document: TextDocument = models.ForeignKey(
        "TextDocument",
        on_delete=models.CASCADE,
        related_name="text_paragraphs",
    )
    agenda_item: AgendaItem = models.ForeignKey(
        "agenda.AgendaItem",
        on_delete=models.CASCADE,
        related_name="text_paragraphs",
        null=True,  # Normally no, forced in serializer
    )

    exporters = {"meeting": {"meeting_kw": "agenda_item__meeting"}}
    importers = {
        "meeting": {},
        "organisation": {"remap_relations": {"user": "last_modified_by"}},
    }

    @property
    def tag(self):
        return f"{self.text_document.base_tag}-{self.paragraph_id}"

    @property
    def meeting(self) -> Meeting | None:
        """While not directly related, it still good to be able to do lookups this way"""
        if self.agenda_item:
            return self.agenda_item.meeting

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["paragraph_id", "text_document"],
                name="paragraph_id_unique_for_text",
            )
        ]

    def save(self, **kw):
        """
        Set paragraph_id when initially saving if it isn't set
        """
        if not self.pk and not self.paragraph_id:
            max_val = self.agenda_item.text_paragraphs.aggregate(
                max_val=models.Max("paragraph_id")
            )["max_val"]
            if max_val is not None:
                self.paragraph_id = max_val + 1
        super().save(**kw)

    # Annotations
    objects: models.Manager
    proposals: models.QuerySet


class DiffProposal(Proposal):
    name = "diff_proposal"
    paragraph: TextParagraph = models.ForeignKey(
        TextParagraph, on_delete=models.RESTRICT, related_name="proposals"
    )

    exporters = {"meeting": {"meeting_kw": "agenda_item__meeting"}}
    importers = {
        "meeting": {
            "remap_relations": {
                "text_paragraph": {"paragraph"},
                "proposal": {"proposal_ptr"},
            }
        },
        "organisation": {
            "remap_relations": {
                "text_paragraph": {"paragraph"},
                "proposal": {"proposal_ptr"},
            }
        },
    }

    def save(self, **kw):
        """
        Force paragraph tag
        """
        if self.paragraph.tag not in self.tags:
            self.tags.append(self.paragraph.tag)
        super().save(**kw)


def _new_proposal_id(proposal: Proposal) -> str:
    # FIXME: Do something nice here that isn't just random
    return "".join(sample(ascii_lowercase, 8))
