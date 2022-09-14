from __future__ import annotations
from abc import ABC
from abc import abstractmethod
from typing import Optional

from typing import TYPE_CHECKING

from pydantic import BaseModel
from typing import Type


if TYPE_CHECKING:
    from voteit.meeting.models import MeetingComponent
    from voteit.meeting.models import Meeting


class MeetingComponentAdapter(ABC):
    """
    Handles data for components

    schema
        A Pydantic schema for validation. If it's none, this component has no data.

    multiple
        If meetings can have multiple instances of this component.
    """

    schema: Optional[Type[BaseModel]] = None
    multiple: bool = False

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique name of component
        """

    @property
    @abstractmethod
    def title(self) -> str:
        """
        Human-readable title
        """

    def __init__(self, component: MeetingComponent):
        self.component = component
