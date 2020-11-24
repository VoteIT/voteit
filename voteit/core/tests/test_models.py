from django.contrib.auth.models import User
from django.dispatch import receiver
from django.test import TestCase


class RolesTests(TestCase):
    # The roles tests use the MeetingRoles class instead, since it's kind of hard to test abstract db models in django

    def setUp(self):
        from voteit.meeting.models import MeetingRoles
        from voteit.meeting.models import Meeting

        self.user = User.objects.create(username="jane")
        self.meeting = Meeting.objects.create()
        self.roles = MeetingRoles.objects.create(user=self.user, context=self.meeting)
        self.ROLES = MeetingRoles.valid_roles

    def test_get_required_roles(self):
        participant = self.ROLES["participant"]
        proposer = self.ROLES["proposer"]
        discusser = self.ROLES["discusser"]
        self.assertEqual(
            {participant, proposer}, self.roles.get_required_roles(proposer)
        )
        self.assertEqual({participant}, self.roles.get_required_roles(participant))
        self.assertEqual(
            {participant, discusser}, self.roles.get_required_roles(discusser)
        )

    def test_get_reverse_required_roles(self):
        participant = self.ROLES["participant"]
        proposer = self.ROLES["proposer"]
        discusser = self.ROLES["discusser"]
        potential_voter = self.ROLES["potential_voter"]
        moderator = self.ROLES["moderator"]
        self.assertEqual({proposer}, self.roles.get_reverse_required_roles(proposer))
        self.assertEqual(
            {participant, proposer, discusser, potential_voter, moderator},
            self.roles.get_reverse_required_roles(participant),
        )
        self.assertEqual({discusser}, self.roles.get_reverse_required_roles(discusser))

    def test_add_role(self):
        participant = self.ROLES["participant"]
        self.assertNotIn(participant, self.roles)
        self.roles.add(participant)
        self.assertIn(participant, self.roles)

    def test_remove_role(self):
        participant = self.ROLES["participant"]
        self.roles.add(participant)
        self.assertIn(participant, self.roles)
        self.roles.remove(participant)
        self.assertNotIn(participant, self.roles)

    def test_set_invalid_role(self):
        from voteit.organisation.roles import ROLE_MEETING_CREATOR

        self.assertRaises(AssertionError, self.roles.add, ROLE_MEETING_CREATOR)

    def test_role_requirement_add(self):
        participant = self.ROLES["participant"]
        proposer = self.ROLES["proposer"]
        self.roles.add(proposer)
        self.assertIn(participant, self.roles)
        self.assertIn(proposer, self.roles)

    def test_role_requirement_remove(self):
        participant = self.ROLES["participant"]
        proposer = self.ROLES["proposer"]
        self.roles.add(proposer)
        self.assertIn(participant, self.roles)
        self.assertIn(proposer, self.roles)
        # This will cause proposer to be removed too since it doesn't work without participant
        self.roles.remove(participant)
        self.assertNotIn(participant, self.roles)
        self.assertNotIn(proposer, self.roles)

    def test_signal_roles_added(self):
        from voteit.core.signals import roles_added
        from voteit.meeting.models import MeetingRoles

        participant = self.ROLES["participant"]
        proposer = self.ROLES["proposer"]
        L = []

        @receiver(roles_added, sender=MeetingRoles)
        def my_listener(roles=(), **kw):
            L.extend(roles)

        self.roles.add(proposer)
        self.assertIn(proposer, L)
        self.assertIn(participant, L)

    def test_signal_roles_removed(self):
        from voteit.core.signals import roles_removed
        from voteit.meeting.models import MeetingRoles

        participant = self.ROLES["participant"]
        proposer = self.ROLES["proposer"]
        L = []
        self.roles.add(proposer)

        @receiver(roles_removed, sender=MeetingRoles)
        def my_listener(roles=(), **kw):
            L.extend(roles)

        self.roles.remove(participant)
        self.assertIn(proposer, L)
        self.assertIn(participant, L)
