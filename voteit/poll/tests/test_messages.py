from django.test import TestCase
from django.test import override_settings

from envelope.messages.errors import UnauthorizedError


_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AddVoteTests(TestCase):
    """Since this is an abstract class, we'll use simple vote to test it"""

    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister

        cls.er = ElectoralRegister.objects.create()
        cls.voter = cls.er.voters.create(username="voter")
        cls.poll = Poll.objects.create(electoral_register=cls.er, method_name="simple")
        cls.poll.proposals.create()
        cls.poll.upcoming()
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

    def test_add(self):
        self.poll.ongoing()
        self.poll.save()
        msg = self._mk_one()
        msg.run_job()
        vote = self.poll.votes.filter(user=self.voter).first()
        self.assertIsNotNone(vote)
        self.assertEqual("yes", vote.vote_data)

    def test_add_not_started(self):
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_add_closed_poll(self):
        self.poll.ongoing()
        self.poll.close()
        self.poll.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_add_vote_exists(self):
        from voteit.poll.messages import ChangeVote

        # from voteit.poll.app.polls import simple

        self.poll.ongoing()
        self.poll.save()
        self.vote = self.poll.votes.create(user=self.voter, vote_data="no")
        msg = self._mk_one()
        response = msg.run_job()
        self.assertIsInstance(response, ChangeVote)
        response.run_job()
        vote = self.poll.votes.filter(user=self.voter).first()
        self.assertEqual("yes", vote.vote_data)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AbstainTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister

        cls.er = ElectoralRegister.objects.create()
        cls.voter = cls.er.voters.create(username="voter")
        cls.poll = Poll.objects.create(electoral_register=cls.er, method_name="simple")
        cls.poll.proposals.create()
        cls.poll.upcoming()
        cls.poll.ongoing()
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

    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister

        self.er = ElectoralRegister.objects.create()
        self.voter = self.er.voters.create(username="voter")
        self.poll = Poll.objects.create(
            electoral_register=self.er, method_name="simple"
        )
        self.poll.proposals.create()
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.save()
        self.vote = self.poll.votes.create(user=self.voter, vote_data="yes")

    @property
    def _cut(self):
        from voteit.poll.app.polls.simple import ChangeSimpleVote

        return ChangeSimpleVote

    def _mk_one(self, **kw):
        kw.setdefault("vote", {"choice": "no"})
        kw.setdefault("pk", self.vote.pk)
        return self._cut(mm={"user_pk": self.voter.pk, "consumer_name": "abc"}, **kw)

    def test_change(self):
        msg = self._mk_one()
        msg.run_job()
        self.vote.refresh_from_db()
        self.assertEqual("no", self.vote.vote_data)

    def test_change_closed(self):
        self.poll.close()
        self.poll.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)


#
# @override_settings(CHANNEL_LAYERS=_channel_layers_setting)
# class GetVoteTests(TestCase):
#     """ Tests rely on simple poll method. """
#
#     def setUp(self):
#         from voteit.poll.models import Poll
#         from voteit.poll.models import ElectoralRegister
#
#         self.er = ElectoralRegister.objects.create()
#         self.voter = self.er.voters.create(username="voter")
#         self.poll = Poll.objects.create(
#             electoral_register=self.er, method_name="simple"
#         )
#         self.poll.proposals.create()
#         self.poll.upcoming()
#         self.poll.ongoing()
#         self.poll.save()
#         self.vote = self.poll.votes.create(user=self.voter, vote_data="yes")
#
#     @property
#     def _cut(self):
#         from voteit.poll.messages import GetVote
#
#         return GetVote
#
#     def _mk_one(self, voter=None, **kw):
#         voter = voter or self.voter
#         kw.setdefault("poll", self.poll.pk)
#         return self._cut({"user_pk": voter.pk, "consumer_name": "abc"}, **kw)
#
#     def test_get(self):
#         msg = self._mk_one()
#         response = msg.run_job()
#         self.assertEqual(response.data.vote, self.vote.vote)
#         self.assertEqual(response.data.abstain, False)
#
#     def test_abstain_vote(self):
#         self.vote.abstain = True
#         self.vote.save()
#         msg = self._mk_one()
#         response = msg.run_job()
#         self.assertEqual(response.data.abstain, True)
#
#     def test_no_vote(self):
#         from voteit.messaging.messages.text import TextResponse
#
#         voter = self.er.voters.create(username="second_voter")
#         msg = self._mk_one(voter=voter)
#         response = msg.run_job()
#         self.assertIsInstance(response, TextResponse)
#         self.assertEqual(response.data.msg, "No vote")


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class GetERVoteCountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.poll.models import Poll

        cls.meeting = Meeting.objects.create()
        cls.er = cls.meeting.electoral_registers.create()
        cls.voter_participant = cls.er.voters.create(username="voter1")
        cls.voter_unknown = cls.er.voters.create(username="voter2")
        cls.poll = Poll.objects.create(electoral_register=cls.er, method_name="simple")
        cls.meeting.add_roles(cls.voter_participant, "participant")

    @property
    def _cut(self):
        from voteit.poll.messages import GetERVoteCount

        return GetERVoteCount

    def _mk_one(self, user, **kw):
        kw.setdefault("electoral_register", self.er.pk)
        return self._cut(mm={"user_pk": user.pk, "consumer_name": "abc"}, **kw)

    def test_get(self):
        from voteit.poll.messages import ERVoteCount

        msg = self._mk_one(self.voter_participant)
        response = msg.run_job()
        self.assertIsInstance(response, ERVoteCount)
        self.assertEqual(response.data.total, 2)
        self.assertEqual(
            {self.voter_participant.pk, self.voter_unknown.pk},
            set([x.user for x in response.data.weights]),
        )

    def test_get_unauthorized_user(self):
        msg = self._mk_one(self.voter_unknown)
        self.assertRaises(UnauthorizedError, msg.run_job)
