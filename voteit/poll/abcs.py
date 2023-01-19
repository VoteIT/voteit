from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from collections import Counter
from logging import getLogger
from random import shuffle
from typing import TYPE_CHECKING

from pydantic.main import BaseModel

from voteit.meeting.roles import ROLE_POTENTIAL_VOTER

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from voteit.poll.models import Poll
    from voteit.poll.models import ElectoralRegister
    from voteit.meeting.models import Meeting
    from voteit.meeting.models import MeetingGroup
    from voteit.poll.messages import VoteBase
    from voteit.poll.schemas import PollResult
    from voteit.core.models import User as UserType

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
    handles_group_vote = False
    handles_personal_vote = True

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

    @property
    @abstractmethod
    def handles_vote_weight(self) -> bool:
        """
        Does this method handle vote weight (voters with multiple votes) in any way?
        """

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
        if self.meeting.latest_er is None:
            return True
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

    def create_er(self, force=False, **kwargs) -> ElectoralRegister:
        """
        A default method to create electoral registers.
        There's no need to use this for the policy.
        Some will probably implement their own.
        Note that new electoral registers shouldn't be created unless needed or forced.
        """
        if force or self.new_er_needed(**kwargs):
            # Avoid circular import
            from voteit.poll.signals import new_er_created

            # FIXME: Atomics?
            er = self.meeting.electoral_registers.create(source=self.name)
            er.set_voters_from_dict(self.get_voters(**kwargs))
            self.meeting.latest_er = er  # Clear cached
            new_er_created.send(instance=er, sender=er.__class__)
            return er
        return self.meeting.latest_er


class GroupVoteElectoralRegisterPolicy(ElectoralRegisterPolicy, ABC):
    """
    Handles group voting, and may handle user voting too.
    """

    handles_group_vote = True
    handles_personal_vote = False  # Defaults to false

    def calc_group_votes_equal(
        self, only_users_qs: QuerySet[UserType] | None = None
    ) -> dict[int, int]:
        """
        This is equal-ish, since votes power is an integer.
        Use random distribution for left-overs.
        """
        counter = Counter()
        groups_qs = self.meeting.groups.filter(
            votes__isnull=False, votes__gt=0
        ).prefetch_related("members")
        potential_voters_pks = self.meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER)
        for group in groups_qs:
            group: MeetingGroup
            mqs = group.members.filter(pk__in=potential_voters_pks)
            if only_users_qs is not None:
                mqs = mqs & only_users_qs
            user_pks = list(mqs.values_list("pk", flat=True))
            if not user_pks:
                # Avoid div 0
                continue
            full, rest = divmod(group.votes, len(user_pks))
            for pk in user_pks:
                counter[pk] += full
            if rest:
                shuffle(user_pks)
                for pk in user_pks:
                    counter[pk] += 1
                    rest -= 1
                    if not rest:
                        break
        return dict(counter)
