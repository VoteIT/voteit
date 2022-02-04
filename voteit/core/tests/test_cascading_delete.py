from django.contrib.auth import get_user_model
from voteit.core.testing import FakeCommit
from voteit.meeting.models import Meeting

from voteit.organisation.models import Organisation

User = get_user_model()

from django.test import TestCase


class GenerateValidUseridTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    def setUp(self):
        self.meeting = Meeting.objects.get(pk=1)

    def test_delete(self):
        with FakeCommit():
            self.meeting.delete()
