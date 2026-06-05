from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from voteit.agenda.statemachines import AgendaItemStateMachine
from voteit.core import PERM
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.poll.models import Poll
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Vote
from voteit.meeting.models import Meeting

User = get_user_model()


class PollRulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.ai = cls.meeting.agenda_items.create(meeting=cls.meeting, state="upcoming")
        cls.poll = Poll.objects.create(
            method_name="simple", agenda_item=cls.ai, meeting=cls.meeting
        )
        cls.poll.proposals.create(agenda_item=cls.ai)
        cls.er = ElectoralRegister.objects.create()
        cls.poll.electoral_register = cls.er
        cls.poll.save()
        cls.anon = AnonymousUser()
        cls.outsider = User.objects.create(username="anon")
        cls.participant_user = cls.meeting.participants.create(username="participant")
        cls.voter_user = User.objects.create(username="voter")
        cls.er.set_voters_from_dict({cls.voter_user.pk: 1})
        # Voters should always be participants too
        cls.meeting.add_roles(cls.voter_user, ROLE_PARTICIPANT)
        cls.moderator = cls.meeting.participants.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)

    def setUp(self):
        self.meeting.refresh_from_db()
        self.poll.refresh_from_db()
        self.ai.refresh_from_db()

    def test_is_voter(self):
        from voteit.poll.rules import is_voter

        self.assertFalse(is_voter(self.anon, self.poll))
        self.assertFalse(is_voter(self.outsider, self.poll))
        self.assertTrue(is_voter(self.voter_user, self.poll))

    def test_add_poll_ai(self):
        ADD = Poll.get_perm(PERM.ADD)
        self.assertFalse(self.anon.has_perm(ADD, self.ai))
        self.assertFalse(self.outsider.has_perm(ADD, self.ai))
        self.assertFalse(self.voter_user.has_perm(ADD, self.ai))
        self.assertTrue(self.moderator.has_perm(ADD, self.ai))

    def test_add_poll_standalone_meeting(self):
        ADD = Poll.get_perm(PERM.ADD)
        self.assertFalse(self.anon.has_perm(ADD, self.meeting))
        self.assertFalse(self.outsider.has_perm(ADD, self.meeting))
        self.assertFalse(self.voter_user.has_perm(ADD, self.meeting))
        self.assertTrue(self.moderator.has_perm(ADD, self.meeting))

    def test_add_poll_archived_ai(self):
        self.ai.archive()
        ADD = Poll.get_perm(PERM.ADD)
        self.assertFalse(self.anon.has_perm(ADD, self.ai))
        self.assertFalse(self.outsider.has_perm(ADD, self.ai))
        self.assertFalse(self.voter_user.has_perm(ADD, self.ai))
        self.assertFalse(self.moderator.has_perm(ADD, self.ai))

    def test_add_poll_archived_meeting(self):
        self.meeting.archive()
        ADD = Poll.get_perm(PERM.ADD)
        self.assertFalse(self.anon.has_perm(ADD, self.meeting))
        self.assertFalse(self.outsider.has_perm(ADD, self.meeting))
        self.assertFalse(self.voter_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.moderator.has_perm(ADD, self.meeting))

    def test_change_poll_upcoming(self):
        self.poll.upcoming(force=True)
        CHANGE = Poll.get_perm(PERM.CHANGE)
        self.assertFalse(self.anon.has_perm(CHANGE, self.poll))
        self.assertFalse(self.outsider.has_perm(CHANGE, self.poll))
        self.assertFalse(self.voter_user.has_perm(CHANGE, self.poll))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.poll))

    def test_change_poll_ongoing(self):
        self.poll.state = "ongoing"
        CHANGE = Poll.get_perm(PERM.CHANGE)
        self.assertFalse(self.anon.has_perm(CHANGE, self.poll))
        self.assertFalse(self.outsider.has_perm(CHANGE, self.poll))
        self.assertFalse(self.voter_user.has_perm(CHANGE, self.poll))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.poll))

    def test_change_poll_closed(self):
        self.poll.state = "closed"
        CHANGE = Poll.get_perm(PERM.CHANGE)
        self.assertFalse(self.anon.has_perm(CHANGE, self.poll))
        self.assertFalse(self.outsider.has_perm(CHANGE, self.poll))
        self.assertFalse(self.voter_user.has_perm(CHANGE, self.poll))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.poll))

    def test_delete_poll_upcoming(self):
        self.poll.upcoming(force=True)
        DELETE = Poll.get_perm(PERM.DELETE)
        self.assertFalse(self.anon.has_perm(DELETE, self.poll))
        self.assertFalse(self.outsider.has_perm(DELETE, self.poll))
        self.assertFalse(self.voter_user.has_perm(DELETE, self.poll))
        self.assertTrue(self.moderator.has_perm(DELETE, self.poll))

    def test_delete_poll_ongoing(self):
        self.poll.state = "ongoing"
        DELETE = Poll.get_perm(PERM.DELETE)
        self.assertFalse(self.anon.has_perm(DELETE, self.poll))
        self.assertFalse(self.outsider.has_perm(DELETE, self.poll))
        self.assertFalse(self.voter_user.has_perm(DELETE, self.poll))
        self.assertTrue(self.moderator.has_perm(DELETE, self.poll))

    def test_delete_poll_closed(self):
        self.poll.state = "closed"
        DELETE = Poll.get_perm(PERM.DELETE)
        self.assertFalse(self.anon.has_perm(DELETE, self.poll))
        self.assertFalse(self.outsider.has_perm(DELETE, self.poll))
        self.assertFalse(self.voter_user.has_perm(DELETE, self.poll))
        self.assertTrue(self.moderator.has_perm(DELETE, self.poll))

    def test_delete_poll_closed_ai(self):
        self.poll.state = "closed"
        self.ai.state = AgendaItemStateMachine.closed.value
        DELETE = Poll.get_perm(PERM.DELETE)
        self.assertFalse(self.anon.has_perm(DELETE, self.poll))
        self.assertFalse(self.outsider.has_perm(DELETE, self.poll))
        self.assertFalse(self.voter_user.has_perm(DELETE, self.poll))
        self.assertTrue(self.moderator.has_perm(DELETE, self.poll))

    def test_delete_poll_archived_meeting(self):
        self.poll.state = "finished"
        self.poll.save()
        self.meeting.archive()
        self.meeting.save()
        # Due to state changes
        self.poll.refresh_from_db()
        self.ai.refresh_from_db()
        self.assertEqual("archived", self.meeting.state)
        self.assertEqual("archived", self.ai.state)
        self.assertEqual("finished", self.poll.state)
        DELETE = Poll.get_perm(PERM.DELETE)
        self.assertFalse(self.anon.has_perm(DELETE, self.poll))
        self.assertFalse(self.outsider.has_perm(DELETE, self.poll))
        self.assertFalse(self.voter_user.has_perm(DELETE, self.poll))
        self.assertFalse(self.moderator.has_perm(DELETE, self.poll))

    def test_change_state(self):
        CHANGE_STATE = Poll.get_perm(PERM.CHANGE_STATE)
        self.assertFalse(self.anon.has_perm(CHANGE_STATE, self.poll))
        self.assertFalse(self.outsider.has_perm(CHANGE_STATE, self.poll))
        self.assertFalse(self.voter_user.has_perm(CHANGE_STATE, self.poll))
        self.assertTrue(self.moderator.has_perm(CHANGE_STATE, self.poll))

    def test_change_state_archived(self):
        self.ai.archive()
        self.ai.save()
        CHANGE_STATE = Poll.get_perm(PERM.CHANGE_STATE)
        self.assertFalse(self.anon.has_perm(CHANGE_STATE, self.poll))
        self.assertFalse(self.outsider.has_perm(CHANGE_STATE, self.poll))
        self.assertFalse(self.voter_user.has_perm(CHANGE_STATE, self.poll))
        self.assertFalse(self.moderator.has_perm(CHANGE_STATE, self.poll))


class VoteRulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create(state="ongoing")
        cls.ai = cls.meeting.agenda_items.create(meeting=cls.meeting, state="ongoing")
        cls.poll = Poll.objects.create(
            method_name="simple", agenda_item=cls.ai, meeting=cls.meeting
        )
        cls.poll.proposals.create(agenda_item=cls.ai)
        cls.er = ElectoralRegister.objects.create()
        cls.poll.electoral_register = cls.er
        cls.poll.save()
        cls.anon_user = User.objects.create(username="anon")
        cls.participant_user = cls.meeting.participants.create(username="participant")
        cls.voter_user = User.objects.create(username="voter")
        cls.voted_user = User.objects.create(username="voted")
        cls.er.set_voters_from_dict({cls.voter_user.pk: 1, cls.voted_user.pk: 1})
        cls.anon = AnonymousUser()
        # Voters should always be participants too
        cls.meeting.add_roles(cls.voter_user, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.voted_user, ROLE_PARTICIPANT)
        cls.moderator = cls.meeting.participants.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        # And the voted user have voted of course :)
        cls.vote = cls.poll.votes.create(vote_data="yes", user=cls.voted_user)

    def setUp(self):
        self.poll.refresh_from_db()

    def test_add_upcoming(self):
        self.poll.upcoming(force=True)
        self.poll.save()
        self.assertEqual("upcoming", self.poll.state)
        ADD = Vote.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.poll))
        self.assertFalse(self.participant_user.has_perm(ADD, self.poll))
        self.assertFalse(self.voter_user.has_perm(ADD, self.poll))
        self.assertFalse(self.voted_user.has_perm(ADD, self.poll))
        self.assertFalse(self.moderator.has_perm(ADD, self.poll))
        self.assertFalse(self.anon.has_perm(ADD, self.poll))

    def test_add_ongoing(self):
        self.poll.state = "ongoing"
        self.poll.save()
        self.assertEqual("ongoing", self.poll.state)
        ADD = Vote.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.poll))
        self.assertFalse(self.participant_user.has_perm(ADD, self.poll))
        self.assertTrue(self.voter_user.has_perm(ADD, self.poll))
        self.assertTrue(self.voted_user.has_perm(ADD, self.poll))
        self.assertFalse(self.moderator.has_perm(ADD, self.poll))
        self.assertFalse(self.anon.has_perm(ADD, self.poll))

    def test_add_closed(self):
        self.poll.state = "ongoing"
        self.poll.close(force=True)
        self.poll.save()
        self.assertEqual("finished", self.poll.state)
        ADD = Vote.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.poll))
        self.assertFalse(self.participant_user.has_perm(ADD, self.poll))
        self.assertFalse(self.voter_user.has_perm(ADD, self.poll))
        self.assertFalse(self.voted_user.has_perm(ADD, self.poll))
        self.assertFalse(self.moderator.has_perm(ADD, self.poll))
        self.assertFalse(self.anon.has_perm(ADD, self.poll))

    def test_delete_ongoing(self):
        self.poll.state = "ongoing"
        self.poll.save()
        self.assertEqual("ongoing", self.poll.state)
        DELETE = Vote.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.vote))
        self.assertFalse(self.participant_user.has_perm(DELETE, self.vote))
        self.assertFalse(self.voter_user.has_perm(DELETE, self.vote))
        self.assertTrue(self.voted_user.has_perm(DELETE, self.vote))
        self.assertFalse(self.moderator.has_perm(DELETE, self.vote))
        self.assertFalse(self.anon.has_perm(DELETE, self.vote))

    def test_delete_closed(self):
        self.poll.state = "ongoing"
        self.poll.close(force=True)
        self.poll.save()
        self.assertEqual("finished", self.poll.state)
        DELETE = Vote.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.vote))
        self.assertFalse(self.participant_user.has_perm(DELETE, self.vote))
        self.assertFalse(self.voter_user.has_perm(DELETE, self.vote))
        self.assertFalse(self.voted_user.has_perm(DELETE, self.vote))
        self.assertFalse(self.moderator.has_perm(DELETE, self.vote))
        self.assertFalse(self.anon.has_perm(DELETE, self.vote))

    def test_view(self):
        # View state always behaves the same way
        self.poll.state = "ongoing"
        self.poll.save()
        self.assertEqual("ongoing", self.poll.state)
        VIEW = Vote.get_perm(PERM.VIEW)
        self.assertFalse(self.anon_user.has_perm(VIEW, self.vote))
        self.assertFalse(self.participant_user.has_perm(VIEW, self.vote))
        self.assertFalse(self.voter_user.has_perm(VIEW, self.vote))
        self.assertTrue(self.voted_user.has_perm(VIEW, self.vote))
        self.assertFalse(self.moderator.has_perm(VIEW, self.vote))
        self.assertFalse(self.anon.has_perm(VIEW, self.vote))


class ElectoralRegisterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.er = cls.meeting.electoral_registers.create()
        cls.participant = User.objects.create(username="participant")
        cls.outsider = User.objects.create(username="outsider")
        cls.moderator = User.objects.create(username="moderator")
        cls.anon = AnonymousUser()
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.ADD_PERM = ElectoralRegister.get_perm(PERM.ADD)

    # Note: View tests removed, queryset handles that

    def test_add(self):
        self.assertFalse(self.participant.has_perm(self.ADD_PERM, self.meeting))
        self.assertFalse(self.outsider.has_perm(self.ADD_PERM, self.meeting))
        self.assertFalse(self.anon.has_perm(self.ADD_PERM, self.meeting))
        self.assertTrue(self.moderator.has_perm(self.ADD_PERM, self.meeting))

    def test_add_archived_meeting(self):
        self.meeting.archive()
        self.meeting.save()
        self.assertFalse(self.participant.has_perm(self.ADD_PERM, self.meeting))
        self.assertFalse(self.outsider.has_perm(self.ADD_PERM, self.meeting))
        self.assertFalse(self.anon.has_perm(self.ADD_PERM, self.meeting))
        self.assertFalse(self.moderator.has_perm(self.ADD_PERM, self.meeting))
