from django.contrib.auth.models import User
from django.test import TestCase


class RoleTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.user = User.objects.create(username="jane")
        self.meeting = Meeting.objects.create()

    def tearDown(self):
        from voteit.core.role import roles

        roles.pop("helloclass", None)

    @property
    def _cut(self):
        from voteit.core.role import Role

        return Role

    @property
    def MeetingParticipant(self):
        """ Use this instead since Role is an abstract implementation. """
        from voteit.meeting.rules import is_participant
        from voteit.meeting.models import Meeting

        class MeetingParticipant(self._cut):
            rule = is_participant
            model = Meeting
            m2m_field = "participants"
            title = "Meeting participant"

        return MeetingParticipant

    def _register_helloclass(self):
        from voteit.core.role import roles

        @roles
        class HelloClass(self.MeetingParticipant):
            pass

        return HelloClass

    def test_registration(self):
        from voteit.core.role import roles

        self._register_helloclass()
        self.assertIn("helloclass", roles)

    def test_wrong_instance_type(self):
        self.assertRaises(TypeError, self.MeetingParticipant, object())

    def test_add_role(self):
        participants = self.MeetingParticipant(self.meeting)
        self.assertNotIn(self.user, participants)
        participants.add(self.user)
        self.assertIn(self.user, participants)

    def test_remove_role(self):
        participants = self.MeetingParticipant(self.meeting)
        participants.add(self.user)
        self.assertIn(self.user, participants)
        participants.remove(self.user)
        self.assertNotIn(self.user, participants)

    def test_rule(self):
        participants = self.MeetingParticipant(self.meeting)
        self.assertFalse(participants.allowed(self.user))
        participants.add(self.user)
        self.assertTrue(participants.allowed(self.user))

    def test_valid_roles(self):
        from voteit.core.role import get_valid_roles

        self.assertEqual(set(), set(get_valid_roles(object)))
        self.assertEqual(set(), set(get_valid_roles(self.meeting)))

        HelloClass = self._register_helloclass()

        self.assertEqual({HelloClass}, set(get_valid_roles(self.meeting)))

    def test_assigned_roles(self):
        from voteit.core.role import get_assigned_roles

        HelloClass = self._register_helloclass()

        self.assertEqual(set(), set(get_assigned_roles(self.meeting, self.user)))

        HelloClass(self.meeting).add(self.user)

        self.assertEqual({HelloClass}, set(get_assigned_roles(self.meeting, self.user)))
