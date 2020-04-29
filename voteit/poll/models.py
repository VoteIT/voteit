from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter

from django.contrib.auth.models import User
from django.db import models
from django.db.models import UniqueConstraint
from django.dispatch import receiver
from voteit.core.signals import before_transition
from django.utils.functional import cached_property
from voteit.core.component import FactoryRegistry
from voteit.core.models import WorkflowMixin, BaseContent
from voteit.core.workflow import Transition
from voteit.poll.exceptions import (
    ElectoralRegisterEmpty,
    ElectoralRegisterMissing,
    InvalidPollMethod,
    InvalidProposalCount,
    NotAllowedToVote
)
from voteit.poll.workflow import PollWorkflow


class PollMethod(ABC):
    def __init__(self, poll: Poll):
        self.poll = poll

    @property
    @abstractmethod
    def Vote(self, **kw) -> Vote:
        """ Factory for votes """
        pass

    @property
    @abstractmethod
    def title(self) -> str:
        pass

    def get_result(self):
        """ Return JSON-serializable result.
        """
        counter = Counter()
        for v in self.get_votes():
            if not v.abstain:
                # FIXME: Vote power here
                counter[v.ballot()] += 1
        return counter

    def get_votes(self):
        return self.Vote.objects.filter(poll=self.poll)

    def create(self, **kw):
        kw.setdefault("poll", self.poll)
        return self.Vote.objects.create(**kw)

    def start_check(self):
        """ Make sure all conditions are met before starting the poll with this method.
        """


poll_methods = FactoryRegistry(PollMethod)


class ElectoralRegisterMethod(ABC):
    pass


er_method = FactoryRegistry(ElectoralRegisterMethod)


class ElectoralRegister(models.Model):
    created = models.DateTimeField(editable=False, auto_now_add=True)
    voters = models.ManyToManyField(User)


class Poll(BaseContent, WorkflowMixin):
    wf_name = PollWorkflow.name
    title = models.CharField(max_length=70)
    description = models.CharField(max_length=200)
    proposals = models.ManyToManyField("proposal.Proposal")
    method_name = models.CharField(max_length=20, null=True)
    created = models.DateTimeField(editable=False, auto_now_add=True)
    started = models.DateTimeField(editable=False, null=True)
    closed = models.DateTimeField(editable=False, null=True)
    initial_electoral_register = models.ForeignKey(
        "ElectoralRegister",
        on_delete=models.PROTECT,
        editable=False,
        null=True,
        related_name="polls_initial",
    )
    electoral_register = models.ForeignKey(
        "ElectoralRegister",
        on_delete=models.PROTECT,
        editable=False,
        null=True,
        related_name="poll",
    )

    def change_electoral_register(
        self, electoral_register: ElectoralRegister, user: User
    ):
        self.electoral_register = electoral_register
        # FIXME: Delete all votes from users who aren't in the new registry when the poll closes?

    def start_check(self):
        """ Check that this poll could be started. A very basic check for the most obvious things.
        """
        if self.electoral_register is None:
            raise ElectoralRegisterMissing()
        if self.electoral_register.voters.count() < 1:
            raise ElectoralRegisterEmpty()
        if self.method_name not in poll_methods:
            raise InvalidPollMethod()
        if not isinstance(self.method, PollMethod):
            raise InvalidPollMethod()
        if self.proposals.count() < 1:
            raise InvalidProposalCount("No proposals")
        # And check the specifics for the poll method
        self.method.start_check()

    @cached_property
    def method(self):
        return poll_methods[self.method_name](self)

    def get_votes(self):
        return self.method.get_votes()


class Vote(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    poll = models.ForeignKey("poll.Poll", on_delete=models.CASCADE, related_name="+")
    created = models.DateTimeField(editable=False, auto_now_add=True)
    abstain = models.BooleanField(default=False)

    class Meta:
        abstract = True
        constraints = [
            # FIXME doesn't work?
            UniqueConstraint(
                fields=["user", "poll"],
                name="%(app_label)s_%(class)s_unique_vote_for_user",
            )
        ]

    def __str__(self):
        return f"<{self.__class__.__name} from {self.user}>"

    @abstractmethod
    def ballot(self):
        """ The value we need to care about when calculating the result.
            Must be hashable.
        """
        pass

    def save(self, **kw):
        if not self.poll.electoral_register:
            raise ElectoralRegisterMissing()
        if not self.poll.electoral_register.voters.filter(id=self.user.id):
            raise NotAllowedToVote("Not allowed to vote")
        super().save(**kw)


@receiver(before_transition, sender=Poll)
def start_check_before_actual_transition(sender, instance: Poll, user: User, transition: Transition, *args, **kwargs):
    if transition.to_state == PollWorkflow.ONGOING:
        instance.start_check()


#@receiver(before_transition, sender=Poll)
#def remove_bad_votes(sender, instance, *args, **kwargs):
#    """ When the ElectoralRegister has changed and there are polls that shouldn't be around.
#    """
#    # FIXME: Connect this with some kind of notification
#    pass


# Touch DB models in apps
# FIXME: Is there no smarter way to do this?
from voteit.poll.app import *

