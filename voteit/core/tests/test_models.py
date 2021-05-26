from django.contrib.auth import get_user_model
from django.dispatch import receiver
from django.test import TestCase
from voteit.core.testing import mk_usertag, mk_hashtag


class UserTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.core.models import User

        cls.user = User.objects.create(username="blaha")

    def test_valid_userid_guard(self):
        self.assertFalse(self.user.valid_userid_guard())  # Empty
        self.user.userid = "blaha"
        self.assertTrue(self.user.valid_userid_guard())
        self.user.userid = "äö"
        self.assertFalse(self.user.valid_userid_guard())  # Bad!
        self.user.userid = "ABC"
        self.assertFalse(self.user.valid_userid_guard())  # Bad too!


class RolesTests(TestCase):
    # The roles tests use the MeetingRoles class instead, since it's kind of hard to test abstract db models in django

    def setUp(self):
        from voteit.meeting.models import MeetingRoles
        from voteit.meeting.models import Meeting

        User = get_user_model()
        self.user = User.objects.create(username="jane")
        self.meeting = Meeting.objects.create()
        self.roles = MeetingRoles.objects.create(user=self.user, context=self.meeting)
        self.ROLES = MeetingRoles.valid_roles

    def test_get_roles(self):
        participant = self.ROLES["participant"]
        self.assertIsNone(self.meeting.get_roles(self.user))
        self.roles.add(participant)
        self.roles.save()
        self.assertEqual({participant}, self.meeting.get_roles(self.user))

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

    def test_roles_object_removed_when_assignment_empty(self):
        from voteit.meeting.models import MeetingRoles

        participant = self.ROLES["participant"]

        self.roles.add(participant)
        self.roles.remove(participant)
        # Roles deleted
        self.assertFalse(
            MeetingRoles.objects.filter(user=self.user, context=self.meeting).exists()
        )


class BaseContentTests(TestCase):
    def setUp(self):
        # Testing abstract model through meeting model
        from voteit.meeting.models import Meeting

        User = get_user_model()

        self.meeting = Meeting.objects.create()
        self.user = User.objects.create(username="ivan")

    def test_body_mentions(self):
        self.assertFalse(self.meeting.mentions.filter(pk=self.user.pk).exists())
        self.meeting.body = f"Hello {mk_usertag(self.user.pk)} what's up?"
        self.meeting.save()
        self.assertTrue(self.meeting.mentions.filter(pk=self.user.pk).exists())

    def test_body_mentions_with_nonexisting_user(self):
        # Shouldn't kill setting text
        deleted_pk = self.user.pk
        self.user.delete()
        self.meeting.body = f"I used to know {mk_usertag(deleted_pk)} once"
        self.meeting.save()
        self.assertFalse(self.meeting.mentions.count())

    def test_body_tags(self):
        self.meeting.body = f"{mk_hashtag('SUP')} all {mk_hashtag('participants')}? {mk_hashtag('KörVi')}!"
        self.meeting.save()
        self.assertEqual(["körvi", "participants", "sup"], self.meeting.tags)

    def test_body_isnt_mangled_by_bleach(self):
        text = f"{mk_hashtag('KörVi')}!"
        self.meeting.body = text
        self.meeting.save()
        self.assertIn("class", text)
        self.assertIn("<span", text)
        self.assertIn("KörVi", text)
        self.assertIn("data-index", text)
        self.assertIn("data-index", text)
        self.assertIn("data-value", text)
        self.assertIn("data-id", text)
        self.assertIn("data-denotation-char", text)
        self.assertEqual(len(text), len(self.meeting.body))

        # self.assertEqual(text, self.meeting.body)
