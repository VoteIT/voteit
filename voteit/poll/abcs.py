from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from logging import getLogger
from typing import TYPE_CHECKING

from pydantic.main import BaseModel

from voteit.core.decorators import ensure_atomic
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.workflows import MeetingWf
from voteit.poll.exceptions import ElectoralRegisterError

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
    settings_schema: type[BaseModel] | None = None
    historic = False

    def __init__(self, poll: Poll):
        self.poll = poll

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of this poll method. It's an attribute on the class"""

    @property
    @abstractmethod
    def vote_schema(self) -> type[BaseModel]:
        """The pydantic schema used to serialize and validate vote data."""

    @property
    @abstractmethod
    def result_schema(self) -> type[PollResult]:
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
    """
    Responsible for handling electoral registers.
    """

    logger = logger
    description: str = ""
    available: bool = True  # Is this manually selectable?
    # Will the method (maybe) result in weighted votes?
    handles_vote_weight: bool = False
    # Is this OK to use together with a manual selection of voters?
    allow_manual: bool = False
    # Can this method be triggered whenever the moderator likes? (In advance of polls for instance)
    allow_trigger: bool = False
    # Will this method update ER for ongoing polls? It will also have the effect
    # that polls can be started with an empty ER.
    allow_poll_er_change = bool = False
    # Is this compatible with active_check?
    handles_active_check: bool = False
    # Does this method require group votes to be disabled or enabled?
    group_votes_active: bool | None = None
    # Can this method handle group votes delegated to other groups?
    handles_delegate_to: bool = False

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
    def get_voters(self, **kwargs) -> dict[int, int]:
        """
        Return a dict with user PKs and vote weight as value

        This returns users that should (currently!) be voters according to this method.
        It doesn't mean that they are voters right now.

        It could simply be the users from potential voters for instance:
        self.meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER)
        """

    def poll_will_have_voters(self, **kwargs) -> bool:
        """
        The method itself needs to be sure that any starting poll must have voters. For instance, if auto
        is used there must be potential voters.

        Normally this is just a quick check that get_voters() return something.
        """
        return self.meeting.roles.filter(
            assigned__contains=[ROLE_POTENTIAL_VOTER]
        ).exists()

    def new_er_needed(self, **kwargs) -> bool:
        """
        Is a new ER needed?
        """
        if self.meeting.state not in (MeetingWf.ONGOING, MeetingWf.UPCOMING):
            return False
        if self.meeting.latest_er is None:
            if self.allow_poll_er_change:
                return True  # We need one regardless of voters
            # No reason to create empty
            return bool(self.get_voters(**kwargs))
        # Create empty is okay if it differs from last ER
        return self.get_voters(**kwargs) != self.meeting.latest_er.weight_dict

    def pre_apply(self, poll: Poll, target: str):
        """
        Some methods create ER on the fly when polls start. Use this hook for those cases.
        """

    def apply(self, poll: Poll, target: str | None = None):
        """
        (Maybe) apply the policy to this poll.
        Target is the workflow state the poll will soon enter, if this was triggered by workflow.
        Note that WF only trigger on upcoming and ongoing
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

    @ensure_atomic
    def create_er(self, force=False, **kwargs) -> ElectoralRegister | None:
        """
        A default method to create electoral registers.
        There's no need to use this for the policy.
        Some will probably implement their own.
        Note that new electoral registers shouldn't be created unless needed or forced.
        """
        if force or self.new_er_needed(**kwargs):
            # Avoid circular import
            from voteit.poll.signals import new_er_created

            if self.group_votes_active is not None:
                if self.group_votes_active != self.meeting.group_votes_active:
                    raise ElectoralRegisterError(
                        "Incompatible electoral register method. InviteGroup votes must be %s."
                        % self.group_votes_active
                        and "active"
                        or "inactive"
                    )
            voters = self.get_voters(**kwargs)
            er = self.meeting.electoral_registers.create(source=self.name)
            er.set_voters_from_dict(voters)
            self.meeting.latest_er = er  # Clear cached
            new_er_created.send(instance=er, sender=er.__class__)
            return er
        return self.meeting.latest_er
