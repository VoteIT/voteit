from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from logging import getLogger
from typing import Optional
from typing import Set
from typing import TYPE_CHECKING
from typing import Type

from pydantic.main import BaseModel

if TYPE_CHECKING:
    from voteit.poll.models import Poll
    from voteit.poll.models import ElectoralRegister
    from voteit.meeting.models import Meeting
    from voteit.poll.messages import VoteBase
    from voteit.poll.schemas import PollResult

logger = getLogger(__name__)


class PollMethod(ABC):
    """
    This is a wrapper for polls that handles calculation of the result
    and the implementation of the poll method.
    """

    poll: Poll
    settings_schema: Optional[Type[BaseModel]] = None

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
        """
        Run extra validation based on how the vote itself looks.
        For instance checking that a ranked vote actually ranks real proposals.
        May raise ValidationErrorMsg in case something goes wrong.
        """

    def start_check(self) -> None:  # pragma: no cover
        """
        Specifics for this poll method except the ones for the base Poll.
        Things like if there's enough proposals to start the poll.
        Raise exceptions for conditions that aren't met.
        """


class ElectoralRegisterPolicy(ABC):
    """Responsible for handling electoral registers."""

    logger = logger

    def __init__(self, meeting: Meeting):
        self.meeting = meeting

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def title(self) -> str:
        ...

    @abstractmethod
    def get_voters(self, **kwargs) -> Set[int]:
        """
        Return a Set with users that should (currently!) be voters according to this method.
        It doesn't mean that they are voters right now.

        It could simply be the users from potential voters for instance:
        self.meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER)
        """

    def new_er_needed(self, **kwargs) -> bool:
        """
        Is a new ER needed?
        """
        if self.meeting.latest_er is None:
            return True
        return self.get_voters(**kwargs) != set(
            self.meeting.latest_er.voters.all().values_list("pk", flat=True)
        )

    def pre_apply(self, poll: Poll, target: str):
        """
        Some methods create ER on the fly when polls start. Use this hook for those cases.
        """

    def apply(self, poll: Poll, target: Optional[str] = None):
        """
        (Maybe) apply the policy to this poll.
        Target is the workflow state the poll will soon enter, if this was triggered by workflow
        """
        self.pre_apply(poll, target)
        meeting = poll.meeting
        if meeting is None:  # pragma: no coverage
            # FIXME: We don't support this yet
            raise Exception("No meeting")
        meetings_er = poll.meeting.latest_er
        if meetings_er is not None:
            if poll.electoral_register is None:
                self.logger.debug(
                    "%s has no electoral register. Attaching %s", poll, meetings_er
                )
                poll.electoral_register = meetings_er
            elif poll.electoral_register != meetings_er:
                self.logger.debug(
                    "%s has an outdated electoral register, changing to %s instead",
                    poll,
                    meetings_er,
                )
                poll.electoral_register = meetings_er
            else:
                self.logger.debug("%s already has the correct electoral register", poll)
                return
            # FIXME: This should probably be wrapped in a transaction
            poll.save()

    def create_er(self, force=False, **kwargs) -> ElectoralRegister:
        """
        A default method to create electoral registers.
        There's no need to use this for the policy.
        Some will probably implement their own.
        Note that new electoral registers shouldn't be created unless needed or forced.
        """
        if force or self.new_er_needed(**kwargs):
            er = self.meeting.electoral_registers.create()
            er.voters.set(self.get_voters(**kwargs))
            self.meeting.latest_er = er  # Clear cached
            return er
        return self.meeting.latest_er
