from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from voteit.meeting.models import Meeting
    from voteit.proposal.models import Proposal
    from voteit.core.models import User as UserType
    from voteit.meeting.models import MeetingGroup


class ProposalIDPolicy(ABC):
    """
    Policy that decides how proposal IDs should be generated
    """

    def __init__(self, meeting: Meeting):
        self.meeting = meeting

    @abstractmethod
    def suggestion(
        self,
        author: UserType | None = None,
        meeting_group: MeetingGroup | None = None,
        **kwargs,
    ) -> str | None:
        """
        Return a suggestion of what the id might look like without numbers
        """

    @abstractmethod
    def __call__(self, proposal: Proposal) -> str:
        """
        Return name suggestion. It should be unique
        """
