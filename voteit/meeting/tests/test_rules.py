from django.contrib.auth import get_user_model
from django.test import TestCase
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.meeting.workflows import MeetingWf

User = get_user_model()


class RulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        cls.meeting = Meeting.objects.create()
        cls.user = User.objects.create(username="a")

    def setUp(self):
        self.meeting.refresh_from_db()
        self.user.refresh_from_db()

    def test_is_participant(self):
        from voteit.meeting.rules import is_participant

        self.assertFalse(is_participant(self.user, self.meeting))
        self.meeting.add_roles(self.user, ROLE_PARTICIPANT)
        self.assertTrue(is_participant(self.user, self.meeting))

    def test_is_potential_voter(self):
        from voteit.meeting.rules import is_potential_voter

        self.assertFalse(is_potential_voter(self.user, self.meeting))
        self.meeting.add_roles(self.user, ROLE_POTENTIAL_VOTER)
        self.assertTrue(is_potential_voter(self.user, self.meeting))

    def test_is_moderator(self):
        from voteit.meeting.rules import is_moderator

        self.assertFalse(is_moderator(self.user, self.meeting))
        self.meeting.add_roles(self.user, ROLE_MODERATOR)
        self.assertTrue(is_moderator(self.user, self.meeting))

    def test_is_discusser(self):
        from voteit.meeting.rules import is_discusser

        self.assertFalse(is_discusser(self.user, self.meeting))
        self.meeting.add_roles(self.user, ROLE_DISCUSSER)
        self.assertTrue(is_discusser(self.user, self.meeting))

    def test_is_proposer(self):
        from voteit.meeting.rules import is_proposer

        self.assertFalse(is_proposer(self.user, self.meeting))
        self.meeting.add_roles(self.user, ROLE_PROPOSER)
        self.assertTrue(is_proposer(self.user, self.meeting))


class MeetingPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.organisation.models import Organisation
        from voteit.organisation.roles import ROLE_MEETING_CREATOR
        from voteit.organisation.roles import ROLE_ORG_MANAGER

        cls.organisation: Organisation = Organisation.objects.create()
        cls.meeting = cls.organisation.meetings.create()
        cls.org_manager = User.objects.create(username="org_manager")
        cls.meeting_creator = User.objects.create(username="meeting_creator")
        cls.organisation.add_roles(cls.org_manager, ROLE_ORG_MANAGER)
        cls.organisation.add_roles(cls.meeting_creator, ROLE_MEETING_CREATOR)
        cls.anon_user = User.objects.create(username="anon")
        cls.moderator = User.objects.create(username="moderator")
        cls.participant = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)

    def setUp(self):
        self.meeting.refresh_from_db()

    def p(self, name):
        from voteit.meeting.permissions import MeetingPermissions

        return getattr(MeetingPermissions, name)

    def test_can_add_meeting(self):
        ADD = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(ADD, self.organisation))
        self.assertTrue(self.meeting_creator.has_perm(ADD, self.organisation))
        self.assertTrue(self.org_manager.has_perm(ADD, self.organisation))

    def test_can_view_meeting(self):
        VIEW = self.p("VIEW")
        self.assertFalse(self.anon_user.has_perm(VIEW, self.meeting))
        self.assertTrue(self.moderator.has_perm(VIEW, self.meeting))
        self.assertTrue(self.participant.has_perm(VIEW, self.meeting))
        self.assertFalse(self.org_manager.has_perm(VIEW, self.meeting))

    def test_can_view_meeting_public(self):
        VIEW = self.p("VIEW")
        self.meeting.public = True
        self.meeting.save()
        self.assertTrue(self.anon_user.has_perm(VIEW, self.meeting))
        self.assertTrue(self.moderator.has_perm(VIEW, self.meeting))
        self.assertTrue(self.participant.has_perm(VIEW, self.meeting))
        self.assertTrue(self.org_manager.has_perm(VIEW, self.meeting))

    def test_can_moderate(self):
        MODERATE = self.p("MODERATE")
        self.assertFalse(self.anon_user.has_perm(MODERATE, self.meeting))
        self.assertTrue(self.moderator.has_perm(MODERATE, self.meeting))
        self.assertFalse(self.participant.has_perm(MODERATE, self.meeting))
        self.assertFalse(self.org_manager.has_perm(MODERATE, self.meeting))

    def test_can_change_meeting(self):
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.org_manager.has_perm(CHANGE, self.meeting))

    def test_can_change_meeting_archived(self):
        self.meeting.archive()
        self.meeting.save()
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.org_manager.has_perm(CHANGE, self.meeting))

    def test_can_change_meeting_archive_requested(self):
        self.meeting.state = MeetingWf.ARCHIVING
        self.meeting.save()
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.org_manager.has_perm(CHANGE, self.meeting))

    def test_can_delete_meeting(self):
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(DELETE, self.meeting))
        self.assertTrue(self.moderator.has_perm(DELETE, self.meeting))
        self.assertFalse(self.participant.has_perm(DELETE, self.meeting))
        self.assertFalse(self.org_manager.has_perm(DELETE, self.meeting))

    def test_can_change_roles(self):
        CHANGE_ROLES = self.p("CHANGE_ROLES")
        self.assertFalse(self.anon_user.has_perm(CHANGE_ROLES, self.meeting))
        self.assertTrue(self.moderator.has_perm(CHANGE_ROLES, self.meeting))
        self.assertFalse(self.participant.has_perm(CHANGE_ROLES, self.meeting))
        self.assertTrue(self.org_manager.has_perm(CHANGE_ROLES, self.meeting))

    def test_can_change_roles_archived(self):
        CHANGE_ROLES = self.p("CHANGE_ROLES")
        self.meeting.archive()
        self.meeting.save()
        self.assertFalse(self.anon_user.has_perm(CHANGE_ROLES, self.meeting))
        self.assertFalse(self.moderator.has_perm(CHANGE_ROLES, self.meeting))
        self.assertFalse(self.participant.has_perm(CHANGE_ROLES, self.meeting))
        self.assertFalse(self.org_manager.has_perm(CHANGE_ROLES, self.meeting))

    def test_can_view_roles(self):
        VIEW_ROLES = self.p("VIEW_ROLES")
        self.assertFalse(self.anon_user.has_perm(VIEW_ROLES, self.meeting))
        self.assertTrue(self.moderator.has_perm(VIEW_ROLES, self.meeting))
        self.assertTrue(self.participant.has_perm(VIEW_ROLES, self.meeting))
        self.assertTrue(self.org_manager.has_perm(VIEW_ROLES, self.meeting))

    def test_can_view_roles_anon(self):
        VIEW_ROLES = self.p("VIEW_ROLES")
        self.meeting.public = True
        self.meeting.save()
        self.assertTrue(self.anon_user.has_perm(VIEW_ROLES, self.meeting))
        self.assertTrue(self.moderator.has_perm(VIEW_ROLES, self.meeting))
        self.assertTrue(self.participant.has_perm(VIEW_ROLES, self.meeting))
        self.assertTrue(self.org_manager.has_perm(VIEW_ROLES, self.meeting))

    def test_can_archive_meeting(self):
        ARCHIVE = self.p("ARCHIVE")
        self.assertFalse(self.anon_user.has_perm(ARCHIVE, self.meeting))
        self.assertTrue(self.moderator.has_perm(ARCHIVE, self.meeting))
        self.assertFalse(self.participant.has_perm(ARCHIVE, self.meeting))
        self.assertFalse(self.org_manager.has_perm(ARCHIVE, self.meeting))

    def test_can_archive_meeting_abort_state(self):
        # Essentially the archive permission is used to request abort too
        self.meeting.state = MeetingWf.ARCHIVING
        self.meeting.save()
        ARCHIVE = self.p("ARCHIVE")
        self.assertFalse(self.anon_user.has_perm(ARCHIVE, self.meeting))
        self.assertTrue(self.moderator.has_perm(ARCHIVE, self.meeting))
        self.assertFalse(self.participant.has_perm(ARCHIVE, self.meeting))
        self.assertFalse(self.org_manager.has_perm(ARCHIVE, self.meeting))


class MeetingGroupPermissionTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.meeting.models import MeetingGroup

        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.meeting_group: MeetingGroup = MeetingGroup.objects.create(
            meeting=cls.meeting
        )
        cls.anon_user = User.objects.create(username="anon")
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")

    def setUp(self):
        self.meeting.refresh_from_db()

    def p(self, name):
        from voteit.meeting.permissions import MeetingGroupPermissions

        return getattr(MeetingGroupPermissions, name)

    def test_can_add(self):
        ADD = self.p("ADD")
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertTrue(self.moderator.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))

    def test_can_add_archived(self):
        ADD = self.p("ADD")

        self.meeting.archive()
        self.meeting.save()
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.moderator.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))

    def test_can_view(self):
        VIEW = self.p("VIEW")
        self.assertFalse(self.anon_user.has_perm(VIEW, self.meeting_group))
        self.assertTrue(self.moderator.has_perm(VIEW, self.meeting_group))
        self.assertTrue(self.participant.has_perm(VIEW, self.meeting_group))

    def test_can_view_meeting_public(self):
        VIEW = self.p("VIEW")
        self.meeting.public = True
        self.meeting.save()
        self.assertTrue(self.anon_user.has_perm(VIEW, self.meeting_group))
        self.assertTrue(self.moderator.has_perm(VIEW, self.meeting_group))
        self.assertTrue(self.participant.has_perm(VIEW, self.meeting_group))

    def test_can_change(self):
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting_group))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.meeting_group))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting_group))

    def test_can_change_archived_meeting(self):
        CHANGE = self.p("CHANGE")
        self.meeting.archive()
        self.meeting.save()
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting_group))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.meeting_group))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting_group))

    def test_can_delete(self):
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(DELETE, self.meeting_group))
        self.assertTrue(self.moderator.has_perm(DELETE, self.meeting_group))
        self.assertFalse(self.participant.has_perm(DELETE, self.meeting_group))

    def test_can_delete_archived_meeting(self):
        DELETE = self.p("DELETE")
        self.meeting.archive()
        self.meeting.save()
        self.assertFalse(self.anon_user.has_perm(DELETE, self.meeting_group))
        self.assertFalse(self.moderator.has_perm(DELETE, self.meeting_group))
        self.assertFalse(self.participant.has_perm(DELETE, self.meeting_group))
