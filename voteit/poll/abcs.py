from __future__ import annotations

from abc import abstractmethod, ABC
from logging import getLogger
from typing import TYPE_CHECKING, Optional
from typing import Type
from pydantic.main import BaseModel
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER

from voteit.poll.schemas import PollResult

if TYPE_CHECKING:
    from voteit.poll.models import Poll
    from voteit.poll.models import ElectoralRegister
    from voteit.meeting.models import Meeting
    from voteit.poll.messages import VoteBase

logger = getLogger(__name__)


class PollMethod(ABC):
    """This is a wrapper for polls that handles calculation of the result
    and the implementation of the poll method.
    """

    poll: Poll

    def __init__(self, poll: Poll):
        self.poll = poll

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of this poll method. It's an attribute on the class"""

    @property
    @abstractmethod
    def vote_schema(self) -> Type[BaseModel]:
        """The pydantic schema used to serialize and validate vote data."""

    @property
    @abstractmethod
    def result_schema(self) -> Type[PollResult]:
        """Pydantic result schema."""

    @property
    def settings_schema(self) -> Optional[Type[BaseModel]]:
        """Pydantic settings schema."""
        return None

    @abstractmethod
    def vote_to_str(self, data: BaseModel) -> str:
        """Take a pydantic instance and turn it into a string that will be suitable
        for storage or calculation of vote result.
        """

    @abstractmethod
    def vote_to_obj(self, text: str) -> BaseModel:
        """Pydantic instance based on vote_schema."""

    @abstractmethod
    def calculate_result(self, counter) -> BaseModel:
        """Takes the counted ballots, calculate the result and store it."""

    def validate_vote(self, msg: VoteBase) -> None:
        """Run extra validation based on how the vote itself looks.
        For instance checking that a ranked vote actually ranks real proposals.
        May raise ValidationErrorMsg in case something goes wrong.
        """

    def start_check(self) -> bool:  # pragma: no cover
        """Specifics for this poll method except the ones for the base Poll.
        Things like if there's enough proposals to start the poll.
        Raise exceptions for conditions that aren't met.
        """
        return True


class ElectoralRegisterPolicy(ABC):
    """Responsible for handling electoral registers."""

    def __init__(self, meeting: Meeting):
        self.meeting = meeting

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def title(self) -> str:
        pass

    @abstractmethod
    def apply(self, poll: Poll):
        """Apply the policy to this poll."""

    def create_er(self, meeting: Meeting) -> ElectoralRegister:
        """A default method to create electoral registers.
        There's no need to use this for the policy.
        Some will probably implement their own.
        """
        from voteit.poll.models import ElectoralRegister

        er = ElectoralRegister.objects.create(meeting=meeting)
        er.voters.set(meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER))
        return er
