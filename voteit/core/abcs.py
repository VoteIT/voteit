from __future__ import annotations

from abc import abstractmethod, ABCMeta

from typing import TYPE_CHECKING, Optional

from django.db import models

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting
    from voteit.agenda.models import AgendaItem


__all__ = ("ABCModel", "AgendaItemContext", "MeetingContext")


class _AbstractModelMeta(ABCMeta, type(models.Model)):
    pass


class ABCModel(models.Model, metaclass=_AbstractModelMeta):
    """Abstract classes based on ABCMeta don't work in django -
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


class AgendaItemContext(ABCModel):
    """ Subclassed by things that have a relation to an agenda item. Even the agenda item itself."""

    @property
    @abstractmethod
    def agenda_item(self) -> Optional[AgendaItem]:
        """ Return the AgendaItem object. Probably a foreign key relation."""
        pass

    class Meta:
        abstract = True


class MeetingContext(ABCModel):
    """ This class may be within the scope of a meeting."""

    @property
    @abstractmethod
    def meeting(self) -> Optional[Meeting]:
        """ Return the meeting object. It could be a ForeignKey relation or something that gets the meeting"""
        pass

    class Meta:
        abstract = True
