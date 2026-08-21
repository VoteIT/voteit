from django.contrib.auth import get_user_model

from django.test import TestCase
from django.test import override_settings
from voteit.messaging.testing import testing_channel_layers_setting

from voteit.meeting.models import Meeting

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class GenerateValidUseridTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture"]

    def setUp(self):
        self.meeting = Meeting.objects.get(pk=1)

    def test_delete(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.meeting.delete()
