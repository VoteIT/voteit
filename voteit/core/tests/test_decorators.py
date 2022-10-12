from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import RequestFactory
from rest_framework.exceptions import PermissionDenied

from voteit.core.decorators import has_perm_drf
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions

SUCCESS = object()
User = get_user_model()


class ViewSetDummy:
    def __init__(self, obj):
        self.obj = obj

    def get_object(self):
        return self.obj

    @has_perm_drf(MeetingPermissions.MODERATE)
    def has_perm_drf(self, request, *args, **kwargs):
        return SUCCESS


class HasPermDRFTests(TestCase):

    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.participant = User.objects.get(username="participant")
        cls.moderator = User.objects.get(username="moderator")

    def _mk_request(self, user):
        request = RequestFactory()
        request.user = user
        return request

    def test_not_allowed(self):
        request = self._mk_request(self.participant)
        view = ViewSetDummy(self.meeting)
        with self.assertRaises(PermissionDenied):
            view.has_perm_drf(request)

    def test_allowed(self):
        request = self._mk_request(self.moderator)
        view = ViewSetDummy(self.meeting)
        self.assertEqual(SUCCESS, view.has_perm_drf(request))
