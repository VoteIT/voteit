from __future__ import annotations

from abc import ABCMeta
from abc import abstractmethod
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
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

    name: str

    class Meta:
        abstract = True


class AuditLogMixin:
    agenda_item: AgendaItem | None
    meeting: Meeting | None

    def get_additional_data(self):
        """
        Annotate logentry with the organisation (o), meeting (m) and agenda item (ai).
        The stats job attributes entries to organisations by "o", so it should be
        set whenever there is one. That may fetch the meeting, at most one query
        per relation since Django caches them on the instance.
        """
        data = {}
        if getattr(self, "name", None) == "agenda_item":
            data["ai"] = self.pk
        elif ai_id := getattr(self, "agenda_item_id", None):
            data["ai"] = ai_id
        # A property on most MeetingContext models, a FK or self on the rest.
        if (meeting := _get_related(self, "meeting")) is not None:
            data["m"] = meeting.pk
            org_id = meeting.organisation_id
        elif not (org_id := getattr(self, "organisation_id", None)):
            org = _get_related(self, "organisation")
            org_id = org.pk if org is not None else None
        if org_id:
            data["o"] = org_id
        return data


def _get_related(instance, attr: str):
    # Within a cascading delete the parent may already be gone.
    try:
        return getattr(instance, attr, None)
    except ObjectDoesNotExist:
        return None


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
