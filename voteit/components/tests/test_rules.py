from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class MeetingComponentPermissionTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting
        from voteit.components.models import MeetingComponent

        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.meeting_component: MeetingComponent = cls.meeting.components.create(
            component_name="print_proposal"
        )
        cls.anon_user = User.objects.create(username="anon")
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")

    def setUp(self):
        self.meeting.refresh_from_db()

    def p(self, name):
        from voteit.components.permissions import MeetingComponentPermissions

        return getattr(MeetingComponentPermissions, name)

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
        self.assertFalse(self.anon_user.has_perm(VIEW, self.meeting_component))
        self.assertTrue(self.moderator.has_perm(VIEW, self.meeting_component))
        self.assertTrue(self.participant.has_perm(VIEW, self.meeting_component))

    def test_can_view_meeting_public(self):
        VIEW = self.p("VIEW")
        self.meeting.public = True
        self.meeting.save()
        self.assertTrue(self.anon_user.has_perm(VIEW, self.meeting_component))
        self.assertTrue(self.moderator.has_perm(VIEW, self.meeting_component))
        self.assertTrue(self.participant.has_perm(VIEW, self.meeting_component))

    def test_can_change(self):
        CHANGE = self.p("CHANGE")
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting_component))
        self.assertTrue(self.moderator.has_perm(CHANGE, self.meeting_component))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting_component))

    def test_can_change_archived_meeting(self):
        CHANGE = self.p("CHANGE")
        self.meeting.archive()
        self.meeting.save()
        self.assertFalse(self.anon_user.has_perm(CHANGE, self.meeting_component))
        self.assertFalse(self.moderator.has_perm(CHANGE, self.meeting_component))
        self.assertFalse(self.participant.has_perm(CHANGE, self.meeting_component))

    def test_can_delete(self):
        DELETE = self.p("DELETE")
        self.assertFalse(self.anon_user.has_perm(DELETE, self.meeting_component))
        self.assertTrue(self.moderator.has_perm(DELETE, self.meeting_component))
        self.assertFalse(self.participant.has_perm(DELETE, self.meeting_component))

    def test_can_delete_archived_meeting(self):
        DELETE = self.p("DELETE")
        self.meeting.archive()
        self.meeting.save()
        self.assertFalse(self.anon_user.has_perm(DELETE, self.meeting_component))
        self.assertFalse(self.moderator.has_perm(DELETE, self.meeting_component))
        self.assertFalse(self.participant.has_perm(DELETE, self.meeting_component))
