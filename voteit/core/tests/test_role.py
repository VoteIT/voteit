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
            name = "meetingparticipant"

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
        self.assertIn("meetingparticipant", roles)

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

        HelloClass = self._register_helloclass()

        self.assertIn(HelloClass, set(get_valid_roles(self.meeting)))

    def test_assigned_roles(self):
        from voteit.core.role import get_assigned_roles

        HelloClass = self._register_helloclass()

        self.assertEqual(set(), set(get_assigned_roles(self.meeting, self.user)))

        HelloClass(self.meeting).add(self.user)

        self.assertIn(HelloClass, set(get_assigned_roles(self.meeting, self.user)))

    def test_role_requirement_add(self):
        from voteit.meeting.roles import Participant
        from voteit.meeting.roles import Proposer
        participants = Participant(self.meeting)
        proposers = Proposer(self.meeting)
        self.assertNotIn(self.user, participants)
        self.assertNotIn(self.user, proposers)
        # Proposer is linked to participants, and thus required.
        proposers.add(self.user)
        self.assertIn(self.user, participants)
        self.assertIn(self.user, proposers)

    def test_role_requirement_remove(self):
        from voteit.meeting.roles import Participant
        from voteit.meeting.roles import Proposer
        participants = Participant(self.meeting)
        proposers = Proposer(self.meeting)
        self.assertNotIn(self.user, participants)
        self.assertNotIn(self.user, proposers)
        # Proposer is linked to participants, and thus required.
        proposers.add(self.user)
        self.assertIn(self.user, participants)
        self.assertIn(self.user, proposers)
        # Removing participant will cause proposer to be removed too
        participants.remove(self.user)
        self.assertNotIn(self.user, participants)
        self.assertNotIn(self.user, proposers)

    def test_role_requirement_other_kind_of_role(self):
        from voteit.organisation.roles import OrgManager
        hello_cls = self._register_helloclass()
        self.assertRaises(TypeError, hello_cls.add_requirement, OrgManager)

    def test_role_requirement_to_self(self):
        hello_cls = self._register_helloclass()
        self.assertRaises(ValueError, hello_cls.add_requirement, hello_cls)
