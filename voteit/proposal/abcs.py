from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from voteit.meeting.models import Meeting
    from voteit.proposal.models import Proposal


class ProposalIDPolicy(ABC):
    """
    Policy that decides how proposal IDs should be generated
    """

    def __init__(self, meeting: Meeting):
        self.meeting = meeting

    @abstractmethod
    def __call__(self, proposal: Proposal) -> str:
        """
        Return name suggestion. It should be unique
        """
