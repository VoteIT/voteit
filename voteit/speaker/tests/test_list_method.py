from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem

User = get_user_model()


class ListMethodTests(TestCase):
    """
    This test uses the class Simple to test the (mostly) abstract class.
    """

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.room = cls.meeting.rooms.create()
        cls.system: SpeakerListSystem = SpeakerListSystem.objects.create(
            method_name="simple", room=cls.room
        )
        cls.speaker_list: SpeakerList = SpeakerList.objects.create(
            speaker_system=cls.system
        )
        for i in range(5):
            cls.speaker_list.speakers.create(username=f"user-{i}")

    def test_shuffle(self):
        current_order = self.speaker_list.order_list
        self.assertEqual(5, len(current_order))
        order_changed = False
        for i in range(5):
            self.speaker_list.shuffle()
            if current_order != self.speaker_list.order_list:
                order_changed = True
                break

        self.assertTrue(order_changed)
