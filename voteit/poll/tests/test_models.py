from django.contrib.auth.models import User
from django.test import TestCase
from voteit.poll.exceptions import ElectoralRegisterMissing, ElectoralRegisterEmpty, InvalidProposalCount


class PollMethodTests(TestCase):
    @property
    def _cut(self):
        from voteit.poll.models import PollMethod

        return PollMethod

    def test_registration(self):
        from voteit.core.component import FactoryRegistry
        from voteit.poll.models import Vote
        poll_method = FactoryRegistry(self._cut)

        class _Vote(Vote):
            pass

        @poll_method
        class HelloMethod(self._cut):
            Vote = _Vote
            title = "Hello"

            def start_check(self):
                pass

        self.assertIn('hellomethod', poll_method)


class PollTests(TestCase):

    @property
    def Poll(self):
        from voteit.poll.models import Poll

        return Poll

    @property
    def ElectoralRegister(self):
        from voteit.poll.models import ElectoralRegister
        return ElectoralRegister

    @property
    def Proposal(self):
        from voteit.proposal.models import Proposal
        return Proposal

    def setUp(self):
        from voteit.poll.app.simple import Simple

        self.poll = self.Poll.objects.create()
        self.user = User.objects.create(username='a')
        self.method = Simple.objects.create()
        self.method.poll = self.poll

    def test_method(self):
        self.assertIsInstance(self.poll.method, self.method.__class__)

    def test_start_check_no_electoral_register(self):
        self.assertRaises(ElectoralRegisterMissing, self.poll.start_check)

    def test_start_check_electoral_register_empty(self):
        self.poll.electoral_register = self.ElectoralRegister.objects.create()
        self.assertRaises(ElectoralRegisterEmpty, self.poll.start_check)

    def test_start_check_no_proposals(self):
        self.poll.electoral_register = er = self.ElectoralRegister.objects.create()
        er.voters.add(self.user)
        self.assertRaises(InvalidProposalCount, self.poll.start_check)

    def test_start_check(self):
        self.poll.electoral_register = er = self.ElectoralRegister.objects.create()
        er.voters.add(self.user)
        prop = self.Proposal.objects.create()
        self.poll.proposals.add(prop)
        self.assertIsNone(self.poll.start_check())

    def test_opening_poll_empty_poll(self):
        self.poll.do_transition(self.poll.workflow.UPCOMING, self.user, force=True)
        self.assertRaises(ElectoralRegisterMissing, self.poll.do_transition, self.poll.workflow.ONGOING, self.user, force=True)

    def test_opening_poll(self):
        self.poll.do_transition(self.poll.workflow.UPCOMING, self.user, force=True)
        self.poll.electoral_register = er = self.ElectoralRegister.objects.create()
        er.voters.add(self.user)
        prop = self.Proposal.objects.create()
        self.poll.proposals.add(prop)
        self.assertIsNotNone(
            self.poll.do_transition(self.poll.workflow.ONGOING, self.user, force=True)
        )
        self.assertEqual(self.poll.workflow.ONGOING, self.poll.wf_state)



    # def test_start_poll(self):
    #     pass
    #
    # def test_close_poll(self):
    #     pass
    #
    # def test_change_electoral_register(self):
    #     pass
    #
    # def test_change_electoral_register_deletes_votes(self):
    #     pass
