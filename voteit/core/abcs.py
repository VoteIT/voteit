from __future__ import annotations

from abc import ABCMeta
from abc import abstractmethod
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting
    from voteit.agenda.models import AgendaItem
    from voteit.organisation.models import Organisation

__all__ = ("ABCModel", "AgendaItemContext", "MeetingContext", "OrganisationContext")


class _AbstractModelMeta(ABCMeta, type(models.Model)):
    pass


class ABCModel(models.Model, metaclass=_AbstractModelMeta):
    """
    Abstract classes based on ABCMeta don't work in django -
    this is a workaround to make them behave correctly.
    Remove this as soon as it's fixed in django.

    name:

        The name of the content type.
        We want all models to have predictable names that are similar to their
        class name or any relation attribute. For instance, a proposals relation to
        an agenda item is called proposal.agenda_item. The name of the AgendaItem
        model should be agenda_item in that case.

        Any model that has None here will get it's name from __name__.lower()
        You can set this instead by doing name = "somename"
    """

    name = None

    class Meta:
        abstract = True


class AuditLogMixin:
    agenda_item: AgendaItem | None
    meeting: Meeting | None

    def get_additional_data(self):
        """
        Annotate logentry with some extra data. Avoid expensive lookups here,
        we can always add annotations to the log afterwards.
        """
        data = {}
        if hasattr(self, "organisation_id") and self.organisation_id:
            data["o"] = self.organisation_id
        if hasattr(self, "meeting_id") and self.meeting_id:
            data["m"] = self.meeting_id
        if hasattr(self, "agenda_item_id") and self.agenda_item_id:
            data["ai"] = self.agenda_item_id
        # Ai specific
        if getattr(self, "name", None) == "agenda_item":
            data["ai"] = self.pk
            if self.meeting_id:
                data["m"] = self.meeting_id
        # Meeting specific
        if getattr(self, "name", None) == "meeting":
            data["m"] = self.pk
            if self.organisation_id:
                data["o"] = self.organisation_id
        return data


class AgendaItemContext(AuditLogMixin, ABCModel):
    """
    Subclassed by things that have a relation to an agenda item. Even the agenda item itself.
    """

    @property
    @abstractmethod
    def agenda_item(self) -> AgendaItem | None:
        """
        Return the AgendaItem object. Probably a foreign key relation.
        """

    class Meta:
        abstract = True


class MeetingContext(AuditLogMixin, ABCModel):
    """
    This class may be within the scope of a meeting.
    """

    @property
    @abstractmethod
    def meeting(self) -> Meeting | None:
        """
        Return the meeting object. It could be a ForeignKey relation or something that gets the meeting
        """

    class Meta:
        abstract = True


class OrganisationContext(AuditLogMixin, ABCModel):
    """
    This class may be within the scope of an organisation.
    """

    @property
    @abstractmethod
    def organisation(self) -> Organisation | None:
        """
        Return the organisation object. It could be a ForeignKey relation or a property
        """

    class Meta:
        abstract = True
