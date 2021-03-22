from django.contrib.auth import get_user_model
from django.test import TestCase
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.roles import ROLE_PROPOSER

User = get_user_model()
class RulesTests(TestCase):

    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.meeting.models import MeetingRoles
        self.meeting = Meeting.objects.create()
        self.user = User.objects.create(username="a")
        self.roles = MeetingRoles.objects.create(user=self.user, context=self.meeting)

    def test_is_participant(self):
        from voteit.meeting.rules import is_participant
        self.assertFalse(is_participant(self.user, self.meeting))
        self.roles.add(ROLE_PARTICIPANT)
        self.assertTrue(is_participant(self.user, self.meeting))

    def test_is_potential_voter(self):
        from voteit.meeting.rules import is_potential_voter
        self.assertFalse(is_potential_voter(self.user, self.meeting))
        self.roles.add(ROLE_POTENTIAL_VOTER)
        self.assertTrue(is_potential_voter(self.user, self.meeting))

    def test_is_moderator(self):
        from voteit.meeting.rules import is_moderator
        self.assertFalse(is_moderator(self.user, self.meeting))
        self.roles.add(ROLE_MODERATOR)
        self.assertTrue(is_moderator(self.user, self.meeting))

    def test_is_discusser(self):
        from voteit.meeting.rules import is_discusser
        self.assertFalse(is_discusser(self.user, self.meeting))
        self.roles.add(ROLE_DISCUSSER)
        self.assertTrue(is_discusser(self.user, self.meeting))

    def test_is_proposer(self):
        from voteit.meeting.rules import is_proposer
        self.assertFalse(is_proposer(self.user, self.meeting))
        self.roles.add(ROLE_PROPOSER)
        self.assertTrue(is_proposer(self.user, self.meeting))


class PermissionTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        self.meeting = Meeting.objects.create()
        self.anon_user = User.objects.create(username="anon")
        self.moderator = User.objects.create(username="moderator")
        self.participant = User.objects.create(username="participant")
        self.meeting.add_roles(self.moderator, ROLE_MODERATOR)
        self.meeting.add_roles(self.participant, ROLE_PARTICIPANT)
        #self.moderators_roles = MeetingRoles.objects.create(user=self.moderator, meeting=self.meeting, assigned=[ROLE_MODERATOR, ROLE_PARTICIPANT])
        #self.partipants_roles = MeetingRoles.objects.create(user=self.participant, meeting=self.meeting, assigned=[ROLE_PARTICIPANT])

    def p(self, name):
        from voteit.meeting.permissions import MeetingPermissions
        return getattr(MeetingPermissions, name)

    def test_can_add_meeting(self):
        from voteit.organisation.roles import ROLE_MEETING_CREATOR, ROLE_ORG_MANAGER
        from voteit.organisation.models import Organisation

        organisation = Organisation.objects.create()
        self.meeting.organisation = organisation
        self.meeting.save()

        org_manager = User.objects.create(username="org_manager")
        meeting_creator = User.objects.create(username="meeting_creator")
        organisation.add_roles(org_manager, ROLE_ORG_MANAGER)
        organisation.add_roles(meeting_creator, ROLE_MEETING_CREATOR)
        #OrganisationRoles.objects.create(user=org_manager, organisation=organisation, assigned=[ROLE_ORG_MANAGER])
        #OrganisationRoles.objects.create(user=meeting_creator, organisation=organisation, assigned=[ROLE_MEETING_CREATOR])
        ADD = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(ADD, organisation))
        self.assertTrue(meeting_creator.has_perm(ADD, organisation))
        self.assertTrue(org_manager.has_perm(ADD, organisation))

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
