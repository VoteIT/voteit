from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from voteit.agenda.workflows import AgendaItemWf

User = get_user_model()


class PollRulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister
        from voteit.poll.workflows import PollWf
        from voteit.meeting.models import Meeting

        cls.PollWf = PollWf
        cls.meeting = Meeting.objects.create()
        cls.ai = cls.meeting.agenda_items.create(meeting=cls.meeting)
        cls.ai.upcoming()
        cls.ai.save()
        cls.poll = Poll.objects.create(
            method_name="simple", agenda_item=cls.ai, meeting=cls.meeting
        )
        cls.poll.proposals.create()
        cls.er = ElectoralRegister.objects.create()
        cls.poll.electoral_register = cls.er
        cls.poll.save()
        cls.anon = AnonymousUser()
        cls.outsider = User.objects.create(username="anon")
        cls.participant_user = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.participant_user, "participant")
        cls.voter_user = cls.er.voters.create(username="voter")
        # Voters should always be participants too
        cls.meeting.add_roles(cls.voter_user, "participant")
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, "moderator")

    def setUp(self):
        self.meeting.refresh_from_db()
        self.poll.refresh_from_db()
        self.ai.refresh_from_db()

    def p(self, perm):
        from voteit.poll.permissions import PollPermissions

        return getattr(PollPermissions, perm)

    def test_is_voter(self):
        from voteit.poll.rules import is_voter

        self.assertFalse(is_voter(self.anon, self.poll))
        self.assertFalse(is_voter(self.outsider, self.poll))
        self.assertTrue(is_voter(self.voter_user, self.poll))

    def test_add_poll_ai(self):
        ADD = self.p("ADD")
        self.assertFalse(self.anon.has_perm(ADD, self.ai))
        self.assertFalse(self.outsider.has_perm(ADD, self.ai))
        self.assertFalse(self.voter_user.has_perm(ADD, self.ai))
        self.assertTrue(self.moderator.has_perm(ADD, self.ai))

    def test_add_poll_standalone_meeting(self):
        ADD = self.p("ADD")
        self.assertFalse(self.anon.has_perm(ADD, self.meeting))
        self.assertFalse(self.outsider.has_perm(ADD, self.meeting))
        self.assertFalse(self.voter_user.has_perm(ADD, self.meeting))
        self.assertTrue(self.moderator.has_perm(ADD, self.meeting))

    def test_add_poll_archived_ai(self):
        self.ai.archive()
        ADD = self.p("ADD")
        self.assertFalse(self.anon.has_perm(ADD, self.ai))
        self.assertFalse(self.outsider.has_perm(ADD, self.ai))
        self.assertFalse(self.voter_user.has_perm(ADD, self.ai))
        self.assertFalse(self.moderator.has_perm(ADD, self.ai))

    def test_add_poll_archived_meeting(self):
        self.meeting.archive()
        ADD = self.p("ADD")
        self.assertFalse(self.anon.has_perm(ADD, self.meeting))
        self.assertFalse(self.outsider.has_perm(ADD, self.meeting))
        self.assertFalse(self.voter_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.moderator.has_perm(ADD, self.meeting))

    def test_change_poll_upcoming(self):
        self.poll.upcoming()
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon.has_perm(CHANGE, self.poll))
        self.assertFalse(self.outsider.has_perm(CHANGE, self.poll))
        self.assertFalse(self.voter_user.has_perm(CHANGE, self.poll))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.poll))

    def test_change_poll_ongoing(self):
        self.poll.state = self.PollWf.ONGOING
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon.has_perm(CHANGE, self.poll))
        self.assertFalse(self.outsider.has_perm(CHANGE, self.poll))
        self.assertFalse(self.voter_user.has_perm(CHANGE, self.poll))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.poll))

    def test_change_poll_closed(self):
        self.poll.state = self.PollWf.CLOSED
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon.has_perm(CHANGE, self.poll))
        self.assertFalse(self.outsider.has_perm(CHANGE, self.poll))
        self.assertFalse(self.voter_user.has_perm(CHANGE, self.poll))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.poll))

    def test_delete_poll_upcoming(self):
        self.poll.upcoming()
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon.has_perm(DELETE, self.poll))
        self.assertFalse(self.outsider.has_perm(DELETE, self.poll))
        self.assertFalse(self.voter_user.has_perm(DELETE, self.poll))
        self.assertTrue(self.moderator.has_perm(DELETE, self.poll))

    def test_delete_poll_ongoing(self):
        self.poll.state = self.PollWf.ONGOING
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon.has_perm(DELETE, self.poll))
        self.assertFalse(self.outsider.has_perm(DELETE, self.poll))
        self.assertFalse(self.voter_user.has_perm(DELETE, self.poll))
        self.assertTrue(self.moderator.has_perm(DELETE, self.poll))

    def test_delete_poll_closed(self):
        self.poll.state = self.PollWf.CLOSED
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon.has_perm(DELETE, self.poll))
        self.assertFalse(self.outsider.has_perm(DELETE, self.poll))
        self.assertFalse(self.voter_user.has_perm(DELETE, self.poll))
        self.assertTrue(self.moderator.has_perm(DELETE, self.poll))

    def test_delete_poll_closed_ai(self):
        self.poll.state = self.PollWf.CLOSED
        self.ai.state = AgendaItemWf.CLOSED
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon.has_perm(DELETE, self.poll))
        self.assertFalse(self.outsider.has_perm(DELETE, self.poll))
        self.assertFalse(self.voter_user.has_perm(DELETE, self.poll))
        self.assertTrue(self.moderator.has_perm(DELETE, self.poll))

    def test_delete_poll_archived_meeting(self):
        self.poll.state = self.PollWf.FINISHED
        self.poll.save()
        self.meeting.archive()
        self.meeting.save()
        # Due to state changes
        self.poll.refresh_from_db()
        self.ai.refresh_from_db()
        self.assertEqual("archived", self.meeting.state)
        self.assertEqual("archived", self.ai.state)
        self.assertEqual("finished", self.poll.state)
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon.has_perm(DELETE, self.poll))
        self.assertFalse(self.outsider.has_perm(DELETE, self.poll))
        self.assertFalse(self.voter_user.has_perm(DELETE, self.poll))
        self.assertFalse(self.moderator.has_perm(DELETE, self.poll))

    def test_view_private_poll_upcoming_ai(self):
        self.assertEqual(self.poll.state, "private")
        self.assertEqual(self.ai.state, "upcoming")
        VIEW = self.p("VIEW")
        self.assertFalse(self.anon.has_perm(VIEW, self.poll))
        self.assertFalse(self.outsider.has_perm(VIEW, self.poll))
        self.assertFalse(self.voter_user.has_perm(VIEW, self.poll))
        self.assertTrue(self.moderator.has_perm(VIEW, self.poll))
        self.assertFalse(self.participant_user.has_perm(VIEW, self.poll))

    def test_view_upcoming_poll_private_ai(self):
        self.ai.unpublish()
        self.ai.save()
        self.poll.upcoming()
        self.assertEqual(self.poll.state, "upcoming")
        self.assertEqual(self.ai.state, "private")
        VIEW = self.p("VIEW")
        self.assertFalse(self.anon.has_perm(VIEW, self.poll))
        self.assertFalse(self.outsider.has_perm(VIEW, self.poll))
        self.assertFalse(self.voter_user.has_perm(VIEW, self.poll))
        self.assertTrue(self.moderator.has_perm(VIEW, self.poll))
        self.assertFalse(self.participant_user.has_perm(VIEW, self.poll))

    def test_view_upcoming_poll_and_ai(self):
        self.poll.upcoming()
        self.assertEqual(self.poll.state, "upcoming")
        self.assertEqual(self.ai.state, "upcoming")
        VIEW = self.p("VIEW")
        self.assertFalse(self.anon.has_perm(VIEW, self.poll))
        self.assertFalse(self.outsider.has_perm(VIEW, self.poll))
        self.assertTrue(self.voter_user.has_perm(VIEW, self.poll))
        self.assertTrue(self.moderator.has_perm(VIEW, self.poll))
        self.assertTrue(self.participant_user.has_perm(VIEW, self.poll))

    def test_view_poll_meeting_only(self):
        self.poll.upcoming()
        self.poll.agenda_item = None
        VIEW = self.p("VIEW")
        self.assertFalse(self.anon.has_perm(VIEW, self.poll))
        self.assertFalse(self.outsider.has_perm(VIEW, self.poll))
        self.assertTrue(self.voter_user.has_perm(VIEW, self.poll))
        self.assertTrue(self.moderator.has_perm(VIEW, self.poll))
        self.assertTrue(self.participant_user.has_perm(VIEW, self.poll))

    def test_view_poll_meeting_only_private_poll(self):
        self.poll.agenda_item = None
        self.assertEqual(self.poll.state, "private")
        VIEW = self.p("VIEW")
        self.assertFalse(self.anon.has_perm(VIEW, self.poll))
        self.assertFalse(self.outsider.has_perm(VIEW, self.poll))
        self.assertFalse(self.voter_user.has_perm(VIEW, self.poll))
        self.assertTrue(self.moderator.has_perm(VIEW, self.poll))
        self.assertFalse(self.participant_user.has_perm(VIEW, self.poll))

    def test_change_state(self):
        CHANGE_STATE = self.p("CHANGE_STATE")
        self.assertFalse(self.anon.has_perm(CHANGE_STATE, self.poll))
        self.assertFalse(self.outsider.has_perm(CHANGE_STATE, self.poll))
        self.assertFalse(self.voter_user.has_perm(CHANGE_STATE, self.poll))
        self.assertTrue(self.moderator.has_perm(CHANGE_STATE, self.poll))

    def test_change_state_archived(self):
        self.ai.archive()
        self.ai.save()
        CHANGE_STATE = self.p("CHANGE_STATE")
        self.assertFalse(self.anon.has_perm(CHANGE_STATE, self.poll))
        self.assertFalse(self.outsider.has_perm(CHANGE_STATE, self.poll))
        self.assertFalse(self.voter_user.has_perm(CHANGE_STATE, self.poll))
        self.assertFalse(self.moderator.has_perm(CHANGE_STATE, self.poll))


class VoteRulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import ElectoralRegister
        from voteit.poll.models import Poll
        from voteit.poll.workflows import PollWf
        from voteit.meeting.models import Meeting

        cls.PollWf = PollWf
        cls.meeting = Meeting.objects.create(state="ongoing")
        cls.ai = cls.meeting.agenda_items.create(meeting=cls.meeting, state="ongoing")
        cls.poll = Poll.objects.create(
            method_name="simple", agenda_item=cls.ai, meeting=cls.meeting
        )
        cls.poll.proposals.create()
        cls.er = ElectoralRegister.objects.create()
        cls.poll.electoral_register = cls.er
        cls.poll.save()
        cls.anon_user = User.objects.create(username="anon")
        cls.participant_user = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.participant_user, "participant")
        cls.voter_user = cls.er.voters.create(username="voter")
        cls.voted_user = cls.er.voters.create(username="voted")
        cls.anon = AnonymousUser()
        # Voters should always be participants too
        cls.meeting.add_roles(cls.voter_user, "participant")
        cls.meeting.add_roles(cls.voted_user, "participant")

        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, "moderator")
        # And the voted user have voted of course :)
        cls.vote = cls.poll.votes.create(vote_data="yes", user=cls.voted_user)

    def setUp(self):
        self.poll.refresh_from_db()

    def p(self, perm):
        from voteit.poll.permissions import VotePermissions

        return getattr(VotePermissions, perm)

    def test_add_upcoming(self):
        self.poll.upcoming()
        self.poll.save()
        self.assertEqual("upcoming", self.poll.state)
        ADD = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(ADD, self.poll))
        self.assertFalse(self.participant_user.has_perm(ADD, self.poll))
        self.assertFalse(self.voter_user.has_perm(ADD, self.poll))
        self.assertFalse(self.voted_user.has_perm(ADD, self.poll))
        self.assertFalse(self.moderator.has_perm(ADD, self.poll))
        self.assertFalse(self.anon.has_perm(ADD, self.poll))

    def test_add_ongoing(self):
        self.poll.state = self.PollWf.ONGOING
        self.poll.save()
        self.assertEqual("ongoing", self.poll.state)
        ADD = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(ADD, self.poll))
        self.assertFalse(self.participant_user.has_perm(ADD, self.poll))
        self.assertTrue(self.voter_user.has_perm(ADD, self.poll))
        self.assertTrue(self.voted_user.has_perm(ADD, self.poll))
        self.assertFalse(self.moderator.has_perm(ADD, self.poll))
        self.assertFalse(self.anon.has_perm(ADD, self.poll))

    def test_add_closed(self):
        self.poll.state = self.PollWf.ONGOING
        self.poll.close()
        self.poll.save()
        self.assertEqual("finished", self.poll.state)
        ADD = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(ADD, self.poll))
        self.assertFalse(self.participant_user.has_perm(ADD, self.poll))
        self.assertFalse(self.voter_user.has_perm(ADD, self.poll))
        self.assertFalse(self.voted_user.has_perm(ADD, self.poll))
        self.assertFalse(self.moderator.has_perm(ADD, self.poll))
        self.assertFalse(self.anon.has_perm(ADD, self.poll))

    def test_delete_ongoing(self):
        self.poll.state = self.PollWf.ONGOING
        self.poll.save()
        self.assertEqual("ongoing", self.poll.state)
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(DELETE, self.vote))
        self.assertFalse(self.participant_user.has_perm(DELETE, self.vote))
        self.assertFalse(self.voter_user.has_perm(DELETE, self.vote))
        self.assertTrue(self.voted_user.has_perm(DELETE, self.vote))
        self.assertFalse(self.moderator.has_perm(DELETE, self.vote))
        self.assertFalse(self.anon.has_perm(DELETE, self.vote))

    def test_delete_closed(self):
        self.poll.state = self.PollWf.ONGOING
        self.poll.close()
        self.poll.save()
        self.assertEqual("finished", self.poll.state)
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(DELETE, self.vote))
        self.assertFalse(self.participant_user.has_perm(DELETE, self.vote))
        self.assertFalse(self.voter_user.has_perm(DELETE, self.vote))
        self.assertFalse(self.voted_user.has_perm(DELETE, self.vote))
        self.assertFalse(self.moderator.has_perm(DELETE, self.vote))
        self.assertFalse(self.anon.has_perm(DELETE, self.vote))

    def test_view(self):
        # View state always behaves the same way
        self.poll.state = self.PollWf.ONGOING
        self.poll.save()
        self.assertEqual("ongoing", self.poll.state)
        VIEW = self.p("VIEW")
        self.assertFalse(self.anon_user.has_perm(VIEW, self.vote))
        self.assertFalse(self.participant_user.has_perm(VIEW, self.vote))
        self.assertFalse(self.voter_user.has_perm(VIEW, self.vote))
        self.assertTrue(self.voted_user.has_perm(VIEW, self.vote))
        self.assertFalse(self.moderator.has_perm(VIEW, self.vote))
        self.assertFalse(self.anon.has_perm(VIEW, self.vote))


class ElectoralRegisterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.poll.permissions import ElectoralRegisterPermissions

        cls.meeting = Meeting.objects.create()
        cls.er = cls.meeting.electoral_registers.create()
        cls.participant = User.objects.create(username="participant")
        cls.outsider = User.objects.create(username="outsider")
        cls.moderator = User.objects.create(username="moderator")
        cls.anon = AnonymousUser()
        cls.meeting.add_roles(cls.participant, "participant")
        cls.meeting.add_roles(cls.moderator, "moderator")
        cls.VIEW_PERM = ElectoralRegisterPermissions.VIEW
        cls.ADD_PERM = ElectoralRegisterPermissions.ADD

    def test_view_normal_meeting(self):
        self.assertTrue(self.participant.has_perm(self.VIEW_PERM, self.er))
        self.assertFalse(self.outsider.has_perm(self.VIEW_PERM, self.er))
        self.assertFalse(self.anon.has_perm(self.VIEW_PERM, self.er))

    def test_view_public_meeting(self):
        self.meeting.public = True
        self.meeting.save()
        self.assertTrue(self.participant.has_perm(self.VIEW_PERM, self.er))
        self.assertTrue(self.outsider.has_perm(self.VIEW_PERM, self.er))
        self.assertFalse(self.anon.has_perm(self.VIEW_PERM, self.er))

    def test_unattached_er(self):
        self.er.meeting = None
        self.er.save()
        self.assertFalse(self.participant.has_perm(self.VIEW_PERM, self.er))
        self.assertFalse(self.outsider.has_perm(self.VIEW_PERM, self.er))
        self.assertFalse(self.anon.has_perm(self.VIEW_PERM, self.er))

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
