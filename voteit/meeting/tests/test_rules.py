from django.contrib.auth.models import User
from django.test import TestCase


class RulesTests(TestCase):

    def setUp(self):
        from voteit.meeting.models import Meeting
        self.meeting = Meeting.objects.create()
        self.user = User.objects.create(username="a")

    def test_is_participant(self):
        from voteit.meeting.rules import is_participant
        self.assertFalse(is_participant(self.user, self.meeting))
        self.meeting.participants.add(self.user)
        self.meeting.save()
        self.assertTrue(is_participant(self.user, self.meeting))

    def test_is_potential_voter(self):
        from voteit.meeting.rules import is_potential_voter
        self.assertFalse(is_potential_voter(self.user, self.meeting))
        self.meeting.potential_voters.add(self.user)
        self.meeting.save()
        self.assertTrue(is_potential_voter(self.user, self.meeting))

    def test_is_moderator(self):
        from voteit.meeting.rules import is_moderator
        self.assertFalse(is_moderator(self.user, self.meeting))
        self.meeting.moderators.add(self.user)
        self.meeting.save()
        self.assertTrue(is_moderator(self.user, self.meeting))

    def test_is_discusser(self):
        from voteit.meeting.rules import is_discusser
        self.assertFalse(is_discusser(self.user, self.meeting))
        self.meeting.discussers.add(self.user)
        self.meeting.save()
        self.assertTrue(is_discusser(self.user, self.meeting))

    def test_is_proposer(self):
        from voteit.meeting.rules import is_proposer
        self.assertFalse(is_proposer(self.user, self.meeting))
        self.meeting.proposers.add(self.user)
        self.meeting.save()
        self.assertTrue(is_proposer(self.user, self.meeting))


class PermissionTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        self.meeting = Meeting.objects.create()
        self.anon_user = User.objects.create(username="anon")
        self.moderator = self.meeting.moderators.create(username="moderator")
        self.participant = self.meeting.participants.create(username="participant")

    def p(self, name):
        from voteit.meeting.permissions import MeetingPermissions
        return getattr(MeetingPermissions, name)

    def test_can_add_meeting(self):
        from voteit.organisation.models import Organisation

        ADD = self.p("ADD")
        organisation = Organisation.objects.create()
        self.meeting.organisation = organisation
        self.meeting.save()
        self.meeting_creator = organisation.meeting_creators.create(username="meeting_creator")
        self.manager = organisation.managers.create(username="manager")
        self.assertFalse(self.anon_user.has_perm(ADD, organisation))
        self.assertTrue(self.meeting_creator.has_perm(ADD, organisation))
        self.assertTrue(self.manager.has_perm(ADD, organisation))

    def test_can_view_meeting(self):
        VIEW = self.p("VIEW")
        self.assertFalse(self.anon_user.has_perm(VIEW, self.meeting))
        self.assertTrue(self.moderator.has_perm(VIEW, self.meeting))
        self.assertTrue(self.participant.has_perm(VIEW, self.meeting))

    def test_can_view_meeting_public(self):
        VIEW = self.p("VIEW")
        self.meeting.public = True
        self.meeting.save()
        self.assertTrue(self.anon_user.has_perm(VIEW, self.meeting))
        self.assertTrue(self.moderator.has_perm(VIEW, self.meeting))
        self.assertTrue(self.participant.has_perm(VIEW, self.meeting))

    def test_can_moderate(self):
        MODERATE = self.p("MODERATE")
        self.assertFalse(self.anon_user.has_perm(MODERATE, self.meeting))
        self.assertTrue(self.moderator.has_perm(MODERATE, self.meeting))
        self.assertFalse(self.participant.has_perm(MODERATE, self.meeting))

    def test_can_change_meeting(self):
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting))

    def test_can_delete_meeting(self):
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(DELETE, self.meeting))
        self.assertTrue(self.moderator.has_perm(DELETE, self.meeting))
        self.assertFalse(self.participant.has_perm(DELETE, self.meeting))
