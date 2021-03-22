from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase


class ModeratorApprovedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_MODERATOR
        from voteit.access_policy.app.policies.moderator_approved import (
            ModeratorApprovedAccess,
        )

        User = get_user_model()
        self.meeting = Meeting.objects.create()
        self.moderator = User.objects.create(username="moderator")
        self.meeting.add_roles(self.moderator, ROLE_MODERATOR)
        self.user = User.objects.create(username="user")
        self.ap = ModeratorApprovedAccess.objects.create(meeting=self.meeting)

    def test_request_access(self):
        self.assertFalse(self.ap.unhandled_requests_qs.count())

        self.ap.request_access(self.user, "Hello world")
        self.assertTrue(self.ap.unhandled_requests_qs.count())
        ar = self.ap.unhandled_requests_qs.first()
        self.assertEqual("Hello world", ar.message)

    def test_request_access_several_times(self):
        self.ap.request_access(self.user)
        self.assertRaises(ValueError, self.ap.request_access, self.user)


class AccessRequestTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_MODERATOR
        from voteit.access_policy.app.policies.moderator_approved import (
            ModeratorApprovedAccess,
        )

        User = get_user_model()
        self.meeting = Meeting.objects.create()
        self.moderator = User.objects.create(username="moderator")
        self.meeting.add_roles(self.moderator, ROLE_MODERATOR)
        self.user = User.objects.create(username="user")
        self.ap = ModeratorApprovedAccess.objects.create(meeting=self.meeting)

    @property
    def AccessRequest(self):
        from voteit.access_policy.app.policies.moderator_approved import AccessRequest

        return AccessRequest

    def test_accept(self):
        from voteit.meeting.rules import is_moderator
        from voteit.meeting.rules import is_participant

        ar = self.ap.request_access(self.user)
        self.assertEqual("unhandled", ar.state)
        give_roles = ["participant", "moderator"]
        ar.accept(self.moderator, give_roles, message="Welcome")
        self.assertEqual("accepted", ar.state)
        self.assertEqual("Welcome", ar.moderator_message)
        self.assertIsInstance(ar.handled_ts, datetime)
        self.assertEqual(self.moderator, ar.handled_by)
        self.assertEqual(["participant", "moderator"], ar.roles_given)
        self.assertTrue(is_moderator(self.user, self.meeting))
        self.assertTrue(is_participant(self.user, self.meeting))

    def test_reject(self):
        ar = self.ap.request_access(self.user)
        self.assertEqual("unhandled", ar.state)
        ar.reject(self.moderator, message="No no")
        self.assertEqual("rejected", ar.state)
        self.assertEqual("No no", ar.moderator_message)
        self.assertIsInstance(ar.handled_ts, datetime)
        self.assertEqual(self.moderator, ar.handled_by)
        self.assertFalse(ar.roles_given)

    def test_reset(self):
        ar = self.ap.request_access(self.user)
        ar.reject(self.moderator, message="No no")
        self.assertEqual("rejected", ar.state)
        self.assertEqual("No no", ar.moderator_message)
        self.assertIsInstance(ar.handled_ts, datetime)
        self.assertEqual(self.moderator, ar.handled_by)
        ar.reset()
        self.assertEqual("unhandled", ar.state)
        self.assertIsNone(ar.moderator_message)
        self.assertIsNone(ar.handled_ts)
        self.assertIsNone(ar.handled_by)
