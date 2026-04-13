from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.core import PERM
from voteit.meeting import PERM_CHANGE_DIALECT
from voteit.meeting.models import GroupMembership
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.meeting.workflows import MeetingWf
from voteit.organisation.models import Organisation
from voteit.organisation.roles import ROLE_MEETING_CREATOR

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
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.organisation: Organisation = Organisation.objects.get(pk=1)
        cls.meeting = cls.organisation.meetings.get(pk=1)
        cls.org_manager = cls.organisation.users.get(username="org_manager")
        cls.meeting_creator = cls.organisation.users.create(username="meeting_creator")
        cls.organisation.add_roles(cls.meeting_creator, ROLE_MEETING_CREATOR)
        cls.anon_user = User.objects.create(username="anon")
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")

    def setUp(self):
        self.meeting.refresh_from_db()

    def test_can_add_meeting(self):
        ADD = Meeting.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.organisation))
        self.assertTrue(self.meeting_creator.has_perm(ADD, self.organisation))
        self.assertTrue(self.org_manager.has_perm(ADD, self.organisation))

    def test_can_view_meeting(self):
        VIEW = Meeting.get_perm(PERM.VIEW)
        self.assertFalse(self.anon_user.has_perm(VIEW, self.meeting))
        self.assertTrue(self.moderator.has_perm(VIEW, self.meeting))
        self.assertTrue(self.participant.has_perm(VIEW, self.meeting))
        self.assertFalse(self.org_manager.has_perm(VIEW, self.meeting))
        self.meeting.public = True
        self.meeting.save()
        # Same nowdays
        self.assertFalse(self.anon_user.has_perm(VIEW, self.meeting))
        self.assertTrue(self.moderator.has_perm(VIEW, self.meeting))
        self.assertTrue(self.participant.has_perm(VIEW, self.meeting))
        self.assertFalse(self.org_manager.has_perm(VIEW, self.meeting))

    def test_can_moderate(self):
        MODERATE = Meeting.get_perm(PERM.MODERATE)
        self.assertFalse(self.anon_user.has_perm(MODERATE, self.meeting))
        self.assertTrue(self.moderator.has_perm(MODERATE, self.meeting))
        self.assertFalse(self.participant.has_perm(MODERATE, self.meeting))
        self.assertFalse(self.org_manager.has_perm(MODERATE, self.meeting))

    def test_can_change_meeting(self):
        CHANGE = Meeting.get_perm(PERM.CHANGE)
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.org_manager.has_perm(CHANGE, self.meeting))

    def test_can_change_meeting_archived(self):
        self.meeting.archive()
        self.meeting.save()
        CHANGE = Meeting.get_perm(PERM.CHANGE)
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.org_manager.has_perm(CHANGE, self.meeting))

    def test_can_change_meeting_archive_requested(self):
        self.meeting.state = MeetingWf.ARCHIVING
        self.meeting.save()
        CHANGE = Meeting.get_perm(PERM.CHANGE)
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting))
        self.assertFalse(self.org_manager.has_perm(CHANGE, self.meeting))

    def test_can_change_dialect(self):
        CHANGE_DIALECT = Meeting.get_perm(PERM_CHANGE_DIALECT)
        self.assertFalse(self.anon_user.has_perm(CHANGE_DIALECT, self.meeting))
        self.assertTrue(self.moderator.has_perm(CHANGE_DIALECT, self.meeting))
        self.assertFalse(self.participant.has_perm(CHANGE_DIALECT, self.meeting))
        self.assertFalse(self.org_manager.has_perm(CHANGE_DIALECT, self.meeting))

    def test_can_change_dialect_ongoing(self):
        self.meeting.state = MeetingWf.ONGOING
        self.meeting.save()
        CHANGE_DIALECT = Meeting.get_perm(PERM_CHANGE_DIALECT)
        self.assertFalse(self.anon_user.has_perm(CHANGE_DIALECT, self.meeting))
        self.assertFalse(self.moderator.has_perm(CHANGE_DIALECT, self.meeting))
        self.assertFalse(self.participant.has_perm(CHANGE_DIALECT, self.meeting))
        self.assertFalse(self.org_manager.has_perm(CHANGE_DIALECT, self.meeting))

    def test_can_delete_meeting(self):
        DELETE = Meeting.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.meeting))
        self.assertTrue(self.moderator.has_perm(DELETE, self.meeting))
        self.assertFalse(self.participant.has_perm(DELETE, self.meeting))
        self.assertFalse(self.org_manager.has_perm(DELETE, self.meeting))

    def test_can_change_roles(self):
        CHANGE_ROLES = Meeting.get_perm(PERM.CHANGE_ROLES)
        self.assertFalse(self.anon_user.has_perm(CHANGE_ROLES, self.meeting))
        self.assertTrue(self.moderator.has_perm(CHANGE_ROLES, self.meeting))
        self.assertFalse(self.participant.has_perm(CHANGE_ROLES, self.meeting))
        # They need to join/set their own role as moderator first
        self.assertFalse(self.org_manager.has_perm(CHANGE_ROLES, self.meeting))

    def test_can_change_roles_archived(self):
        CHANGE_ROLES = Meeting.get_perm(PERM.CHANGE_ROLES)
        self.meeting.archive()
        self.meeting.save()
        self.assertFalse(self.anon_user.has_perm(CHANGE_ROLES, self.meeting))
        self.assertFalse(self.moderator.has_perm(CHANGE_ROLES, self.meeting))
        self.assertFalse(self.participant.has_perm(CHANGE_ROLES, self.meeting))
        self.assertFalse(self.org_manager.has_perm(CHANGE_ROLES, self.meeting))

    def test_can_view_roles(self):
        VIEW_ROLES = Meeting.get_perm(PERM.VIEW_ROLES)
        self.assertFalse(self.anon_user.has_perm(VIEW_ROLES, self.meeting))
        self.assertTrue(self.moderator.has_perm(VIEW_ROLES, self.meeting))
        self.assertFalse(self.participant.has_perm(VIEW_ROLES, self.meeting))
        # Join meeting first
        self.assertFalse(self.org_manager.has_perm(VIEW_ROLES, self.meeting))
        self.meeting.public = True
        self.meeting.save()
        self.assertFalse(self.anon_user.has_perm(VIEW_ROLES, self.meeting))
        self.assertTrue(self.moderator.has_perm(VIEW_ROLES, self.meeting))
        self.assertFalse(self.participant.has_perm(VIEW_ROLES, self.meeting))
        self.assertFalse(self.org_manager.has_perm(VIEW_ROLES, self.meeting))

    def test_can_archive_meeting(self):
        ARCHIVE = Meeting.get_perm(PERM.ARCHIVE)
        self.assertFalse(self.anon_user.has_perm(ARCHIVE, self.meeting))
        self.assertTrue(self.moderator.has_perm(ARCHIVE, self.meeting))
        self.assertFalse(self.participant.has_perm(ARCHIVE, self.meeting))
        self.assertFalse(self.org_manager.has_perm(ARCHIVE, self.meeting))

    def test_can_archive_meeting_abort_state(self):
        # Essentially the archive permission is used to request abort too
        self.meeting.state = MeetingWf.ARCHIVING
        self.meeting.save()
        ARCHIVE = Meeting.get_perm(PERM.ARCHIVE)
        self.assertFalse(self.anon_user.has_perm(ARCHIVE, self.meeting))
        self.assertTrue(self.moderator.has_perm(ARCHIVE, self.meeting))
        self.assertFalse(self.participant.has_perm(ARCHIVE, self.meeting))
        self.assertFalse(self.org_manager.has_perm(ARCHIVE, self.meeting))


class MeetingGroupPermissionTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.meeting_group: MeetingGroup = MeetingGroup.objects.create(
            meeting=cls.meeting
        )
        cls.anon_user = User.objects.create(username="anon")
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")

    def setUp(self):
        self.meeting.refresh_from_db()

    def test_can_add(self):
        ADD = MeetingGroup.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertTrue(self.moderator.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))

    def test_can_add_archived(self):
        ADD = MeetingGroup.get_perm(PERM.ADD)
        self.meeting.archive()
        self.meeting.save()
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.moderator.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))

    def test_can_view(self):
        VIEW = MeetingGroup.get_perm(PERM.VIEW)
        self.assertFalse(self.anon_user.has_perm(VIEW, self.meeting_group))
        self.assertTrue(self.moderator.has_perm(VIEW, self.meeting_group))
        self.assertTrue(self.participant.has_perm(VIEW, self.meeting_group))

    def test_can_view_meeting_public(self):
        VIEW = MeetingGroup.get_perm(PERM.VIEW)
        self.meeting.public = True
        self.meeting.save()
        # We've changed the queryset here
        self.assertFalse(self.anon_user.has_perm(VIEW, self.meeting_group))
        self.assertTrue(self.moderator.has_perm(VIEW, self.meeting_group))
        self.assertTrue(self.participant.has_perm(VIEW, self.meeting_group))

    def test_can_change(self):
        CHANGE = MeetingGroup.get_perm(PERM.CHANGE)
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting_group))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.meeting_group))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting_group))

    def test_can_change_archived_meeting(self):
        CHANGE = MeetingGroup.get_perm(PERM.CHANGE)
        self.meeting.archive()
        self.meeting.save()
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting_group))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.meeting_group))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting_group))

    def test_can_delete(self):
        DELETE = MeetingGroup.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.meeting_group))
        self.assertTrue(self.moderator.has_perm(DELETE, self.meeting_group))
        self.assertFalse(self.participant.has_perm(DELETE, self.meeting_group))

    def test_can_delete_archived_meeting(self):
        DELETE = MeetingGroup.get_perm(PERM.DELETE)
        self.meeting.archive()
        self.meeting.save()
        self.assertFalse(self.anon_user.has_perm(DELETE, self.meeting_group))
        self.assertFalse(self.moderator.has_perm(DELETE, self.meeting_group))
        self.assertFalse(self.participant.has_perm(DELETE, self.meeting_group))


class GroupMembershipPermissionTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.meeting_group: MeetingGroup = MeetingGroup.objects.create(
            meeting=cls.meeting
        )
        cls.anon_user = User.objects.create(username="anon")
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.group_membership: GroupMembership = cls.meeting_group.memberships.create(
            user=cls.participant
        )

    def setUp(self):
        self.meeting.refresh_from_db()

    def test_can_add(self):
        ADD = GroupMembership.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting_group))
        self.assertTrue(self.moderator.has_perm(ADD, self.meeting_group))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting_group))

    def test_can_add_archived(self):
        ADD = GroupMembership.get_perm(PERM.ADD)
        self.meeting.archive()
        self.meeting.save()
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting_group))
        self.assertFalse(self.moderator.has_perm(ADD, self.meeting_group))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting_group))

    def test_can_change(self):
        CHANGE = GroupMembership.get_perm(PERM.CHANGE)
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.group_membership))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.group_membership))
        self.assertFalse(self.participant.has_perm(CHANGE, self.group_membership))

    def test_can_change_archived_meeting(self):
        CHANGE = GroupMembership.get_perm(PERM.CHANGE)
        self.meeting.archive()
        self.meeting.save()
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.group_membership))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.group_membership))
        self.assertFalse(self.participant.has_perm(CHANGE, self.group_membership))

    def test_can_delete(self):
        DELETE = GroupMembership.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.group_membership))
        self.assertTrue(self.moderator.has_perm(DELETE, self.group_membership))
        self.assertFalse(self.participant.has_perm(DELETE, self.group_membership))

    def test_can_delete_archived_meeting(self):
        DELETE = GroupMembership.get_perm(PERM.DELETE)
        self.meeting.archive()
        self.meeting.save()
        self.assertFalse(self.anon_user.has_perm(DELETE, self.group_membership))
        self.assertFalse(self.moderator.has_perm(DELETE, self.group_membership))
        self.assertFalse(self.participant.has_perm(DELETE, self.group_membership))
