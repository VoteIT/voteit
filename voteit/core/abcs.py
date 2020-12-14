from __future__ import annotations

from abc import abstractmethod, ABCMeta

from typing import TYPE_CHECKING, Optional

from django.db import models

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting


class _AbstractModelMeta(ABCMeta, type(models.Model)):
    pass


class ABCModel(models.Model, metaclass=_AbstractModelMeta):
    """ Abstract classes based on ABCMeta don't work in django -
        this is a workaround to make them behave correctly.
        Remove this as soon as it's fixed in django.
    """

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
