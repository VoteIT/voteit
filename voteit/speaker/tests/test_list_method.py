from django.contrib.auth.models import User
from django.test import TestCase


class SimpleListMethodTests(TestCase):
    """ This test should also cover the abstract class ListMethod,
        since it's easier to handle the testing within a simple implementation.
    """

    def setUp(self):
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList
        from voteit.speaker.app.list_methods.simple import Simple
        self.method = Simple.objects.create()
        self.system = SpeakerListSystem.objects.create(method=self.method)
        self.speaker_list = SpeakerList.objects.create(list_system=self.system)
        self.speaker_user = User.objects.create_user("speaker")

    def test_method(self):
        pass