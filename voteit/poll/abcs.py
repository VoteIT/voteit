from __future__ import annotations

from abc import abstractmethod
from collections import Counter
from typing import Type, List
from typing import TYPE_CHECKING

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.db.models import UniqueConstraint
from django.utils.translation import gettext_lazy as _
from django.utils.functional import cached_property

from voteit.poll.exceptions import ElectoralRegisterMissing, InvalidProposalCount
from voteit.poll.exceptions import NotAllowedToVote

if TYPE_CHECKING:
    from voteit.poll.models import Poll


class PollMethod(models.Model):
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

    def get_result(self):
        """ Return JSON-serializable result.
        """
        counter = Counter()
        for v in self.get_votes():
            if not v.abstain:
                counter[v.ballot()] += v.weight
        return counter

    def start_check(self):
        """ Make sure all conditions are met before starting the poll with this method.
        """


class MultipleWinnerPollMethod(PollMethod):
    """ Common features for polls with multiple winners.
    """
    min_winners: int = 2
    min_losers: int = 0

    winners: int = models.PositiveSmallIntegerField(_('Winners'))
    min_selected: int = models.PositiveSmallIntegerField(
        _('Minimum selected proposals'), default=1,
        help_text=_('Voter must rank at least this many proposals to cast vote.')
    )

    class Meta:
        abstract = True

    def start_check(self):
        if self.poll.proposals.count() < (self.winners + self.min_losers):
            raise InvalidProposalCount(
                _('The method %(method)s require at least %(min_losers)d more proposals than winners') % {
                    'method': self.title,
                    'min_losers': self.min_losers
                }
            )
        if self.winners < self.min_winners:
            raise InvalidProposalCount(
                _('The method %(method)s require at least %(min_winners)d winner(s)') % {
                    'method': self.title,
                    'min_winners': self.min_winners
                }
            )


class Vote(models.Model):
    user: User = models.ForeignKey(User, on_delete=models.PROTECT)
    created = models.DateTimeField(editable=False, auto_now_add=True)
    changed = models.DateTimeField(editable=False, auto_now=True)
    abstain = models.BooleanField(default=False)

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

    def __str__(self):
        return f"<{self.__class__.__name__} from {self.user}>"

    @property
    def weight(self) -> int:
        return self.method.poll.get_vote_weight(self.user)

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
    ranking: str = models.TextField(_('ranking'))

    class Meta:
        abstract = True

    @property
    def ballot(self) -> List[int]:
        """ Returns a list of proposal primary keys.
        """
        return [int(r) for r in self.ranking.split(',')]


class ElectoralRegisterPolicy(models.Model):
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
