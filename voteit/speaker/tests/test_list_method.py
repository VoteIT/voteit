from django.contrib.auth import get_user_model
from django.test import TestCase


User = get_user_model()


class ListMethodTests(TestCase):
    """This test should also cover the abstract class ListMethod,
    since it's easier to handle the testing within a simple implementation.
    """

    def setUp(self):
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        self.system = SpeakerListSystem.objects.create(method_name="simple")
        self.speaker_list = SpeakerList.objects.create(speaker_system=self.system)
        self.speaker_user = User.objects.create_user("speaker")

    def test_method(self):
        pass
