from __future__ import annotations

from abc import abstractmethod
from collections import Counter
from datetime import datetime
from logging import getLogger
from typing import TYPE_CHECKING
from typing import Type

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.db.models import UniqueConstraint
from django.utils.translation import gettext_lazy as _

from voteit.core.models import ABCModel
from voteit.poll.exceptions import ElectoralRegisterMissing
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.exceptions import NotAllowedToVote

if TYPE_CHECKING:
    from voteit.poll.models import Poll


logger = getLogger(__name__)


class PollMethod(ABCModel):

    poll_rel = GenericRelation(
        "poll.Poll", object_id_field="method_id", content_type_field="method_type"
    )

    class Meta:
        abstract = True

    @property
    def poll(self) -> Poll:
        return self.poll_rel.get()

    @property
    @abstractmethod
    def title(self) -> str:
        pass

    @property
    @abstractmethod
    def vote_set(self) -> models.Manager:
        """ Return the Manager for this implementations Vote model.
            See voteit.poll.app.simple for example
        """

    @property
    @abstractmethod
    def vote_model(self) -> Type[Vote]:
        pass

    def create_vote(self, **kw) -> Vote:
        """ Create vote from factory. """
        # FIXME: Not sure about this since DRF seems to have another idea
        kw.setdefault("method", self)
        return self.vote_model.objects.create(**kw)

    def get_votes(self):
        return self.vote_set.all()

    @abstractmethod
    def calculate_result(self, ballots: Counter):
        """ Takes the counted ballots, calculate the result and store it.
            Return the result in same format as get_result
        """

    @abstractmethod
    def get_result(self):
        """ Return JSON-serializable result of this poll.
        """

    def start_check(self):
        """ Make sure all conditions are met before starting the poll with this method.
        """


class MultipleWinnerPollMethod(PollMethod):
    """ Common features for polls with multiple winners.
    """

    min_winners: int = 2
    min_losers: int = 0

    winners: int = models.PositiveSmallIntegerField(_("Winners"))
    min_selected: int = models.PositiveSmallIntegerField(
        _("Minimum selected proposals"),
        default=1,
        help_text=_("Voter must rank at least this many proposals to cast vote."),
    )

    class Meta:
        abstract = True

    def start_check(self):
        if self.poll.proposals.count() < (self.winners + self.min_losers):
            raise InvalidProposalCount(
                _(
                    "The method %(method)s require at least %(min_losers)d more proposals than winners"
                )
                % {"method": self.title, "min_losers": self.min_losers}
            )
        if self.winners < self.min_winners:
            raise InvalidProposalCount(
                _("The method %(method)s require at least %(min_winners)d winner(s)")
                % {"method": self.title, "min_winners": self.min_winners}
            )


class Vote(ABCModel):
    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT
    )
    created: datetime = models.DateTimeField(editable=False, auto_now_add=True)
    changed: datetime = models.DateTimeField(editable=False, auto_now=True)
    abstain: bool = models.BooleanField(default=False)

    @property
    @abstractmethod
    def method(self) -> PollMethod:
        """ A relation to the poll_method used, for instance:
            method = models.ForeignKey(Simple, on_delete=models.CASCADE, related_name="vote_set")
        """
        pass

    class Meta:
        abstract = True
        constraints = [
            UniqueConstraint(
                fields=["user", "method"],
                name="%(app_label)s_%(class)s_unique_vote_for_user",
            )
        ]

    def __str__(self):  # pragma: no cover
        return f"<{self.__class__.__name__} from {self.user}>"

    @property
    def weight(self) -> int:
        return self.method.poll.electoral_register.get_voter_weight(self.user)

    @property
    @abstractmethod
    def ballot(self):
        """ The value we need to care about when calculating the result.
            Must be hashable.
        """
        pass

    def save(self, **kw):
        er = self.method.poll.electoral_register
        if not er:
            raise ElectoralRegisterMissing()
        if not er.voters.filter(id=self.user.id):
            raise NotAllowedToVote("Not allowed to vote")
        super().save(**kw)

    # Instantiate this manually for type hinting
    objects = models.Manager()


class RankedVote(Vote):
    ranking: str = models.TextField(_("ranking"), editable=False, null=True)

    class Meta:
        abstract = True

    @property
    def ballot(self) -> str:
        """ Returns a list of proposal primary keys.
        """
        return self.ranking


class ElectoralRegisterPolicy(ABCModel):
    """ Responsible for handling electoral registers.
    """

    class Meta:
        abstract = True

    @property
    @abstractmethod
    def title(self) -> str:
        pass

    @abstractmethod
    def apply(self, poll: Poll):
        pass
