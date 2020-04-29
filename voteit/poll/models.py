from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
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
    NotAllowedToVote,
)
from voteit.poll.workflow import PollWorkflow


class PollMethod(models.Model):
    poll_rel = GenericRelation(
        "poll.Poll", object_id_field="method_id", content_type_field="method_type"
    )

    class Meta:
        abstract = True

    @property
    def poll(self):
        return self._poll

    @poll.setter
    def poll(self, poll: Poll):
        self.poll_rel.set([poll])

    @cached_property
    def _poll(self):
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
    def vote_factory(self) -> Vote:
        pass

    def create_vote(self, **kw) -> Vote:
        """ Create vote from factory. """
        # FIXME: Not sure about this since DRF seems to have another idea
        kw.setdefault("method", self)
        return self.vote_factory.objects.create(**kw)

    def get_votes(self):
        return self.vote_set.all()

    def get_result(self):
        """ Return JSON-serializable result.
        """
        counter = Counter()
        for v in self.get_votes():
            if not v.abstain:
                # FIXME: Vote power here
                counter[v.ballot()] += 1
        return counter

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
    method_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True)
    method_id = models.PositiveIntegerField(null=True)
    method = GenericForeignKey("method_type", "method_id")
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

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["method_type", "method_id"],
                name="%(app_label)s_%(class)s_method",
            )
        ]

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
        if not isinstance(self.method, PollMethod):
            raise InvalidPollMethod()
        if self.proposals.count() < 1:
            raise InvalidProposalCount("No proposals")
        # And check the specifics for the poll method
        self.method.start_check()

    def get_votes(self):
        return self.method.get_votes()


class Vote(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    created = models.DateTimeField(editable=False, auto_now_add=True)
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
        return f"<{self.__class__.__name} from {self.user}>"

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


@receiver(before_transition, sender=Poll)
def start_check_before_actual_transition(
    sender, instance: Poll, user: User, transition: Transition, *args, **kwargs
):
    if transition.to_state == PollWorkflow.ONGOING:
        instance.start_check()


# @receiver(before_transition, sender=Poll)
# def remove_bad_votes(sender, instance, *args, **kwargs):
#    """ When the ElectoralRegister has changed and there are polls that shouldn't be around.
#    """
#    # FIXME: Connect this with some kind of notification
#    pass


# Touch DB models in apps
# FIXME: Is there no smarter way to do this?
from voteit.poll.app import *
