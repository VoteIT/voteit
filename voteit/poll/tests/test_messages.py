from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from envelope.messages.errors import UnauthorizedError

from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll

_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


User = get_user_model()


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AddVoteTests(TestCase):
    """Since this is an abstract class, we'll use simple vote to test it"""

    @classmethod
    def setUpTestData(cls):
        cls.er: ElectoralRegister = ElectoralRegister.objects.create()
        cls.voter = User.objects.create(username="voter")
        cls.er.set_voters_from_dict({cls.voter.pk: 1})
        cls.poll: Poll = Poll.objects.create(
            electoral_register=cls.er, method_name="simple"
        )
        cls.poll.proposals.create()
        cls.poll.upcoming(force=True)
        cls.poll.save()

    def setUp(self):
        self.poll.refresh_from_db()

    @property
    def _cut(self):
        from voteit.poll.app.polls.simple import AddSimpleVote

        return AddSimpleVote

    def _mk_one(self, **kw):
        kw.setdefault("vote", {"choice": "yes"})
        kw.setdefault("poll", self.poll.pk)
        return self._cut(mm={"user_pk": self.voter.pk, "consumer_name": "abc"}, **kw)

    def test_add_and_change(self):
        self.poll.ongoing(force=True)
        self.poll.save()
        msg = self._mk_one()
        msg.run_job()
        vote = self.poll.votes.filter(user=self.voter).first()
        self.assertIsNotNone(vote)
        self.assertEqual("yes", vote.vote_data)
        # And make sure it works to do twice
        msg = self._mk_one(vote={"choice": "no"})
        msg.run_job()
        vote.refresh_from_db()
        self.assertEqual({"choice": "no"}, vote.vote.dict())

    def test_add_not_started(self):
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_add_closed_poll(self):
        self.poll.ongoing(force=True)
        self.poll.close(force=True)
        self.poll.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_add_vote_exists(self):
        self.poll.ongoing(force=True)
        self.poll.save()
        self.vote = self.poll.votes.create(user=self.voter, vote_data="no")
        msg = self._mk_one()
        msg.run_job()
        vote = self.poll.votes.filter(user=self.voter).first()
        self.assertEqual("yes", vote.vote_data)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AbstainTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.er: ElectoralRegister = ElectoralRegister.objects.create()
        cls.voter = User.objects.create(username="voter")
        cls.er.set_voters_from_dict({cls.voter.pk: 1})
        cls.poll: Poll = Poll.objects.create(
            electoral_register=cls.er, method_name="simple"
        )
        cls.poll.proposals.create()
        cls.poll.upcoming(force=True)
        cls.poll.ongoing(force=True)
        cls.poll.save()

    def setUp(self):
        self.poll.refresh_from_db()

    @property
    def _cut(self):
        from voteit.poll.messages import AbstainVote

        return AbstainVote

    def _mk_one(self, **kw):
        kw.setdefault("poll", self.poll.pk)
        return self._cut(mm={"user_pk": self.voter.pk, "consumer_name": "abc"}, **kw)

    def test_abstain(self):
        msg = self._mk_one()
        msg.run_job()
        vote = self.poll.votes.filter(user=self.voter).first()
        self.assertIsNotNone(vote)
        self.assertIs(vote.vote_data, None)
        self.assertIs(vote.abstain, True)

    def test_abstain_existing(self):
        from voteit.poll.app.polls.simple import AddSimpleVote

        AddSimpleVote(
            mm={"user_pk": self.voter.pk, "consumer_name": "abc"},
            vote={"choice": "yes"},
            poll=self.poll.pk,
        ).run_job()
        self.test_abstain()


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class ChangeVoteTests(TestCase):
    """Since this is an abstract class, we'll use simple vote to test it"""

    @classmethod
    def setUpTestData(cls):
        cls.er: ElectoralRegister = ElectoralRegister.objects.create()
        cls.voter = User.objects.create(username="voter")
        cls.er.set_voters_from_dict({cls.voter.pk: 1})
        cls.poll: Poll = Poll.objects.create(
            electoral_register=cls.er, method_name="simple"
        )
        cls.poll.proposals.create()
        cls.poll.upcoming(force=True)
        cls.poll.ongoing(force=True)
        cls.poll.save()
        cls.vote = cls.poll.votes.create(user=cls.voter, vote_data="yes")

    @property
    def _cut(self):
        from voteit.poll.app.polls.simple import AddSimpleVote

        return AddSimpleVote

    def _mk_one(self, **kw):
        kw.setdefault("vote", {"choice": "no"})
        kw.setdefault("poll", self.poll.pk)
        return self._cut(mm={"user_pk": self.voter.pk, "consumer_name": "abc"}, **kw)

    def test_change(self):
        msg = self._mk_one()
        msg.run_job()
        self.vote.refresh_from_db()
        self.assertEqual("no", self.vote.vote_data)

    def test_change_closed(self):
        self.poll.close(force=True)
        self.poll.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)
