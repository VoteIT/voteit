from django.contrib.auth.models import User
from django.dispatch import receiver
from django.test import TestCase


class RoleTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.user = User.objects.create(username="jane")
        self.meeting = Meeting.objects.create()

    @property
    def _cut(self):
        from voteit.core.role import Role

        return Role

    def setup_registry(self):
        from voteit.core.role import RoleRegistry
        return RoleRegistry(self._cut)

    @property
    def MeetingParticipant(self):
        """ Use this instead since Role is an abstract implementation. """
        from voteit.meeting.models import Meeting

        class MeetingParticipant(self._cut):
            model = Meeting
            m2m_field = "participants"
            title = "Meeting participant"
            name = "meetingparticipant"

        return MeetingParticipant

    def _register_helloclass(self, decorator):
        @decorator
        class HelloClass(self.MeetingParticipant):
            pass

        return HelloClass

    def test_registration(self):
        roles = self.setup_registry()
        self._register_helloclass(roles)
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

    def test_valid_roles(self):
        roles = self.setup_registry()
        self.assertEqual(set(), set(roles.get_valid_roles(object)))
        HelloClass = self._register_helloclass(roles)
        self.assertIn(HelloClass, set(roles.get_valid_roles(self.meeting)))

    def test_assigned_roles(self):
        roles = self.setup_registry()

        HelloClass = self._register_helloclass(roles)

        self.assertEqual(set(), set(roles.get_assigned_roles(self.meeting, self.user)))

        HelloClass(self.meeting).add(self.user)

        self.assertIn(HelloClass, set(roles.get_assigned_roles(self.meeting, self.user)))

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
        roles = self.setup_registry()
        roles(OrgManager)
        hello_cls = self._register_helloclass(roles)
        self.assertRaises(TypeError, hello_cls.add_requirement, OrgManager)

    def test_role_requirement_to_self(self):
        roles = self.setup_registry()
        hello_cls = self._register_helloclass(roles)
        self.assertRaises(ValueError, hello_cls.add_requirement, hello_cls)

    def test_signal_role_added(self):
        from voteit.core.signals import role_added
        roles = self.setup_registry()
        HelloClass = self._register_helloclass(roles)

        L = []

        @receiver(role_added, sender=HelloClass)
        def my_listener(users=[], **kw):
            L.extend(users)

        hello = HelloClass(self.meeting)
        hello.add(self.user)
        self.assertIn(self.user, L)

    def test_signal_role_removed(self):
        from voteit.core.signals import role_removed
        roles = self.setup_registry()
        HelloClass = self._register_helloclass(roles)

        L = []

        @receiver(role_removed, sender=HelloClass)
        def my_listener(users=[], **kw):
            L.extend(users)

        hello = HelloClass(self.meeting)
        hello.add(self.user)
        self.assertNotIn(self.user, L)
        hello.remove(self.user)
        self.assertIn(self.user, L)
