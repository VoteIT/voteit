from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting


class MeetingContext(ABC):
    """ This class may be within the scope of a meeting."""

    @property
    @abstractmethod
    def meeting(self) -> Optional[Meeting]:
        """ Return the meeting object. It could be a ForeignKey relation or something that gets the meeting"""
        pass
