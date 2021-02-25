from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase


User = get_user_model()


class PollRulesTests(TestCase):
    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create(meeting=self.meeting)
        self.ai.upcoming()
        self.poll = Poll.objects.create(
            method_name="simple", agenda_item=self.ai, meeting=self.meeting
        )
        self.poll.proposals.create()
        self.er = ElectoralRegister.objects.create()
        self.poll.electoral_register = self.er
        self.poll.save()
        self.anon = AnonymousUser()
        self.outsider = User.objects.create(username="anon")
        self.participant_user = User.objects.create(username="participant")
        self.meeting.add_roles(self.participant_user, "participant")
        self.voter_user = self.er.voters.create(username="voter")
        # Voters should always be participants too
        self.meeting.add_roles(self.voter_user, "participant")
        self.moderator = User.objects.create(username="moderator")
        self.meeting.add_roles(self.moderator, "moderator")

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
        self.poll.upcoming()
        self.poll.ongoing()
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon.has_perm(CHANGE, self.poll))
        self.assertFalse(self.outsider.has_perm(CHANGE, self.poll))
        self.assertFalse(self.voter_user.has_perm(CHANGE, self.poll))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.poll))

    def test_change_poll_closed(self):
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.close()
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
        self.poll.upcoming()
        self.poll.start_check()
        self.poll.ongoing()
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon.has_perm(DELETE, self.poll))
        self.assertFalse(self.outsider.has_perm(DELETE, self.poll))
        self.assertFalse(self.voter_user.has_perm(DELETE, self.poll))
        self.assertTrue(self.moderator.has_perm(DELETE, self.poll))

    def test_delete_poll_closed(self):
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.close()
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon.has_perm(DELETE, self.poll))
        self.assertFalse(self.outsider.has_perm(DELETE, self.poll))
        self.assertFalse(self.voter_user.has_perm(DELETE, self.poll))
        self.assertTrue(self.moderator.has_perm(DELETE, self.poll))

    def test_delete_poll_closed_ai(self):
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.close()
        self.ai.ongoing()
        self.ai.close()
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon.has_perm(DELETE, self.poll))
        self.assertFalse(self.outsider.has_perm(DELETE, self.poll))
        self.assertFalse(self.voter_user.has_perm(DELETE, self.poll))
        self.assertTrue(self.moderator.has_perm(DELETE, self.poll))

    def test_delete_poll_archived_meeting(self):
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.close()
        self.meeting.archive()
        self.ai.refresh_from_db()
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


class VoteRulesTests(TestCase):
    def setUp(self):
        from voteit.poll.models import ElectoralRegister
        from voteit.poll.models import Poll
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create(meeting=self.meeting)
        self.ai.ongoing()
        self.poll = Poll.objects.create(
            method_name="simple", agenda_item=self.ai, meeting=self.meeting
        )
        self.poll.proposals.create()
        self.er = ElectoralRegister.objects.create()
        self.poll.electoral_register = self.er
        self.poll.save()
        self.anon_user = User.objects.create(username="anon")
        self.participant_user = User.objects.create(username="participant")
        self.meeting.add_roles(self.participant_user, "participant")
        self.voter_user = self.er.voters.create(username="voter")
        self.voted_user = self.er.voters.create(username="voted")
        self.anon = AnonymousUser()
        # Voters should always be participants too
        self.meeting.add_roles(self.voter_user, "participant")
        self.meeting.add_roles(self.voted_user, "participant")

        self.moderator = User.objects.create(username="moderator")
        self.meeting.add_roles(self.moderator, "moderator")
        # And the voted user have voted of course :)
        self.vote = self.poll.votes.create(vote_data="yes", user=self.voted_user)

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
        self.poll.upcoming()
        self.poll.ongoing()
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
        self.poll.upcoming()
        self.poll.ongoing()
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

    # We don't need to test change for upcoming, no votes should exist :)
    def test_change_ongoing(self):
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.save()
        self.assertEqual("ongoing", self.poll.state)
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.vote))
        self.assertFalse(self.participant_user.has_perm(CHANGE, self.vote))
        self.assertFalse(self.voter_user.has_perm(CHANGE, self.vote))
        self.assertTrue(self.voted_user.has_perm(CHANGE, self.vote))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.vote))
        self.assertFalse(self.anon.has_perm(CHANGE, self.vote))

    def test_change_closed(self):
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.close()
        self.poll.save()
        self.assertEqual("finished", self.poll.state)
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.vote))
        self.assertFalse(self.participant_user.has_perm(CHANGE, self.vote))
        self.assertFalse(self.voter_user.has_perm(CHANGE, self.vote))
        self.assertFalse(self.voted_user.has_perm(CHANGE, self.vote))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.vote))
        self.assertFalse(self.anon.has_perm(CHANGE, self.vote))

    def test_delete_ongoing(self):
        self.poll.upcoming()
        self.poll.ongoing()
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
        self.poll.upcoming()
        self.poll.ongoing()
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
        self.poll.upcoming()
        self.poll.ongoing()
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
    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.poll.permissions import ElectoralRegisterPermissions

        self.meeting = Meeting.objects.create()
        self.er = self.meeting.electoral_registers.create()
        self.participant = User.objects.create(username="participant")
        self.outsider = User.objects.create(username="outsider")
        self.anon = AnonymousUser()
        self.meeting.add_roles(self.participant, "participant")
        self.VIEW_PERM = ElectoralRegisterPermissions.VIEW

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
