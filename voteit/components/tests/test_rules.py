from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.core import PERM
from voteit.meeting.models import Meeting
from voteit.components.models import MeetingComponent

User = get_user_model()


class MeetingComponentPermissionTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.meeting_component: MeetingComponent = cls.meeting.components.create(
            component_name="print_proposal"
        )
        cls.anon_user = User.objects.create(username="anon")
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")

    def setUp(self):
        self.meeting.refresh_from_db()

    def test_can_add(self):
        ADD = MeetingComponent.get_perm(PERM.ADD)
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertTrue(self.moderator.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))

    def test_can_add_archived(self):
        ADD = MeetingComponent.get_perm(PERM.ADD)
        self.meeting.archive()
        self.meeting.save()
        self.assertFalse(self.anon_user.has_perm(ADD, self.meeting))
        self.assertFalse(self.moderator.has_perm(ADD, self.meeting))
        self.assertFalse(self.participant.has_perm(ADD, self.meeting))

    def test_can_change(self):
        CHANGE = MeetingComponent.get_perm(PERM.CHANGE)
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting_component))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.meeting_component))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting_component))

    def test_can_change_archived_meeting(self):
        CHANGE = MeetingComponent.get_perm(PERM.CHANGE)
        self.meeting.archive()
        self.meeting.save()
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting_component))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.meeting_component))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting_component))

    def test_can_delete(self):
        DELETE = MeetingComponent.get_perm(PERM.DELETE)
        self.assertFalse(self.anon_user.has_perm(DELETE, self.meeting_component))
        self.assertTrue(self.moderator.has_perm(DELETE, self.meeting_component))
        self.assertFalse(self.participant.has_perm(DELETE, self.meeting_component))

    def test_can_delete_archived_meeting(self):
        DELETE = MeetingComponent.get_perm(PERM.DELETE)
        self.meeting.archive()
        self.meeting.save()
        self.assertFalse(self.anon_user.has_perm(DELETE, self.meeting_component))
        self.assertFalse(self.moderator.has_perm(DELETE, self.meeting_component))
        self.assertFalse(self.participant.has_perm(DELETE, self.meeting_component))
