from __future__ import annotations

from abc import abstractmethod
from collections import Counter
from typing import TYPE_CHECKING

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.db.models import UniqueConstraint
from django.utils.functional import cached_property

from voteit.poll.exceptions import ElectoralRegisterMissing
from voteit.poll.exceptions import NotAllowedToVote

if TYPE_CHECKING:
    from voteit.poll.models import Poll
    from voteit.poll.models import Vote


class PollMethod(models.Model):
    poll_rel = GenericRelation(
        "poll.Poll", object_id_field="method_id", content_type_field="method_type"
    )

    class Meta:
        abstract = True

    @property
    def poll(self) -> Poll:
        return self._poll

    @poll.setter
    def poll(self, poll: Poll):
        self.poll_rel.set([poll])

    @cached_property
    def _poll(self) -> Poll:
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
