from django.test import TestCase
from voteit.messaging.errors import UnauthorizedError


class AddVoteTests(TestCase):
    """ Since this is an abstract class, we'll use simple vote to test it"""

    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister
        self.er = ElectoralRegister.objects.create()
        self.voter = self.er.voters.create(username="voter")
        self.poll = Poll.objects.create(electoral_register=self.er, method_name="simple")
        self.poll.proposals.create()
        self.poll.upcoming()

    @property
    def _cut(self):
        from voteit.poll.app.polls.simple import AddSimpleVote

        return AddSimpleVote

    def _mk_one(self, **kw):
        kw.setdefault("vote", {"choice": "yes"})
        kw.setdefault("pk", self.poll.pk)
        return self._cut({"user_pk": self.voter.pk, "consumer_name": "abc"}, **kw)

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
        self.poll.ongoing()
        self.poll.save()
        self.vote = self.poll.votes.create(user=self.voter, vote_data="no")
        msg = self._mk_one()
        response = msg.run_job()
        self.assertIsInstance(response, ChangeVote)
        response.run_job()
        vote = self.poll.votes.filter(user=self.voter).first()
        self.assertEqual("yes", vote.vote_data)


class AbstainTests(TestCase):
    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister
        self.er = ElectoralRegister.objects.create()
        self.voter = self.er.voters.create(username="voter")
        self.poll = Poll.objects.create(electoral_register=self.er, method_name="simple")
        self.poll.proposals.create()
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.save()

    @property
    def _cut(self):
        from voteit.poll.messages import AbstainVote
        return AbstainVote

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.poll.pk)
        return self._cut({"user_pk": self.voter.pk, "consumer_name": "abc"}, **kw)

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
            {"user_pk": self.voter.pk, "consumer_name": "abc"},
            vote={"choice": "yes"},
            pk=self.poll.pk,
        ).run_job()
        self.test_abstain()


class ChangeVoteTests(TestCase):
    """ Since this is an abstract class, we'll use simple vote to test it"""

    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister
        self.er = ElectoralRegister.objects.create()
        self.voter = self.er.voters.create(username="voter")
        self.poll = Poll.objects.create(electoral_register=self.er, method_name="simple")
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
        return self._cut({"user_pk": self.voter.pk, "consumer_name": "abc"}, **kw)

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


class GetVoteTests(TestCase):
    """ Tests rely on simple poll method. """

    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister
        self.er = ElectoralRegister.objects.create()
        self.voter = self.er.voters.create(username="voter")
        self.poll = Poll.objects.create(electoral_register=self.er, method_name="simple")
        self.poll.proposals.create()
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.save()
        self.vote = self.poll.votes.create(user=self.voter, vote_data="yes")

    @property
    def _cut(self):
        from voteit.poll.messages import GetVote

        return GetVote

    def _mk_one(self, voter=None, **kw):
        voter = voter or self.voter
        kw.setdefault("pk", self.poll.pk)
        return self._cut({"user_pk": voter.pk, "consumer_name": "abc"}, **kw)

    def test_get(self):
        msg = self._mk_one()
        response = msg.run_job()
        self.assertEqual(response.data.vote, self.vote.vote)
        self.assertEqual(response.data.abstain, False)

    def test_abstain_vote(self):
        self.vote.abstain = True
        self.vote.save()
        msg = self._mk_one()
        response = msg.run_job()
        self.assertEqual(response.data.abstain, True)

    def test_no_vote(self):
        from voteit.messaging.messages.text import TextResponse
        voter = self.er.voters.create(username="second_voter")
        msg = self._mk_one(voter=voter)
        response = msg.run_job()
        self.assertIsInstance(response, TextResponse)
        self.assertEqual(response.data.msg, "No vote")
