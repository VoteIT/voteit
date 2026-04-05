from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from voteit.meeting.models import Meeting

User = get_user_model()


@override_settings(
    AUTHENTICATION_BACKENDS=["voteit.core.permissions.VerbosePermissionBackend"],
    CHECK_PERMISSION_CONTEXT=True,
)
class VerbosePermissionBackendTests(TestCase):
    """Check against real permissions"""

    def setUp(self):
        self.user = User.objects.create(username="tester")
        self.meeting = Meeting.objects.create()

    def test_permission_contexts(self):
        from voteit.meeting.permissions import MeetingPermissions

        # OK test
        self.assertFalse(self.user.has_perm(MeetingPermissions.VIEW, self.meeting))
        # No target passed
        with self.assertRaises(TypeError):
            self.user.has_perm(MeetingPermissions.VIEW)
        # obj not ok
        self.assertRaises(
            AssertionError, self.user.has_perm, MeetingPermissions.VIEW, object()
        )
        # User is also the wrong type
        self.assertRaises(
            AssertionError, self.user.has_perm, MeetingPermissions.VIEW, self.user
        )
