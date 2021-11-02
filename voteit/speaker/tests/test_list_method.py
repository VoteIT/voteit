from django.contrib.auth import get_user_model
from django.test import TestCase


User = get_user_model()


class ListMethodTests(TestCase):
    """
    This test uses the class Simple to test the (mostly) abstract class.
    """

    @classmethod
    def setUpTestData(cls):
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        cls.system: SpeakerListSystem = SpeakerListSystem.objects.create(
            method_name="simple"
        )
        cls.speaker_list: SpeakerList = SpeakerList.objects.create(
            speaker_system=cls.system
        )
        for i in range(5):
            user = cls.speaker_list.speakers.create(username=f"user-{i}")
            cls.speaker_list.speaker_items.create(user=user, order=i)

    # def test_reorder(self):
    #     pass

    def test_shuffle(self):
        current_order = self.speaker_list.current_order()
        self.assertEqual(5, len(current_order))
        order_changed = False
        for i in range(5):
            self.speaker_list.shuffle()
            if current_order != self.speaker_list.current_order():
                order_changed = True
                break

        self.assertTrue(order_changed)
