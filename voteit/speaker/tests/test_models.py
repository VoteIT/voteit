from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.dispatch import receiver
from django.test import TestCase
from django.utils.timezone import now


class SpeakerTests(TestCase):
    def setUp(self):
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        self.system = SpeakerListSystem.objects.create(method_name="simple")
        self.list = SpeakerList.objects.create(list_system=self.system)
        self.user = User.objects.create(username="jane")

    @property
    def Speaker(self):
        from voteit.speaker.models import Speaker

        return Speaker

    def test_create_sets_order(self):
        user_one = User.objects.create(username="one")
        user_two = User.objects.create(username="two")
        speaker_one = self.list.speaker_items.create(user=user_one)
        speaker_two = self.list.speaker_items.create(user=user_two)
        self.assertEqual(1, speaker_one.order)
        self.assertEqual(2, speaker_two.order)

    def test_start(self):
        speaker = self.list.speaker_items.create(user=self.user)
        speaker.start()
        self.assertIsNone(speaker.order)
        self.assertIsInstance(speaker.started, datetime)

    def test_ended(self):
        speaker = self.list.speaker_items.create(user=self.user)
        speaker.start()
        speaker.seconds = 100
        self.assertEqual(timedelta(seconds=100), speaker.ended - speaker.started)

    def test_current(self):
        # This is cheating since we can only expect it to be the current speaker if some data isn't corrupt ;)
        speaker = self.list.speaker_items.create(user=self.user)
        self.assertFalse(speaker.current)
        speaker.start()
        self.assertTrue(speaker.current)
        speaker.seconds = 1
        self.assertFalse(speaker.current)


class SpeakerListTests(TestCase):
    """ Lists don't work without a method, so these basics should be tested
        with a bare minimal implementation.
    """

    def setUp(self):
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        self.system = SpeakerListSystem.objects.create(method_name="simple")
        self.speaker_list = SpeakerList.objects.create(list_system=self.system)
        self.user_one = User.objects.create(username="one")
        self.user_two = User.objects.create(username="two")
        self.user_three = User.objects.create(username="three")
        self.speaker_one = self.speaker_list.speaker_items.create(user=self.user_one)
        self.speaker_two = self.speaker_list.speaker_items.create(user=self.user_two)
        self.speaker_three = self.speaker_list.speaker_items.create(
            user=self.user_three
        )

    def test_current_order(self):
        self.assertEqual(
            [self.speaker_one.pk, self.speaker_two.pk, self.speaker_three.pk],
            self.speaker_list.current_order(),
        )

    def test_reorder(self):
        self.assertEqual(
            [self.speaker_one.pk, self.speaker_two.pk, self.speaker_three.pk],
            self.speaker_list.reorder(),
        )
        # Change timestamp...
        self.speaker_one.created = now()
        self.speaker_one.save()
        self.assertEqual(
            [self.speaker_two.pk, self.speaker_three.pk, self.speaker_one.pk],
            self.speaker_list.reorder(),
        )

    def test_reorder_signals_on_change(self):
        from voteit.speaker.signals import list_updated
        from voteit.speaker.models import SpeakerList

        L = []

        @receiver(list_updated, sender=SpeakerList)
        def my_listener(instance, queue, **kw):
            L.append(queue)

        self.speaker_list.reorder()
        # No change
        self.assertFalse(L)
        # Changing the order will send event
        self.speaker_one.created = now()
        self.speaker_one.save()
        self.speaker_list.reorder()

        self.assertTrue(L)
        self.assertEqual(
            [self.speaker_two.pk, self.speaker_three.pk, self.speaker_one.pk], L[0]
        )  # First event

    def test_safe_pos_overrides_order(self):
        self.speaker_two.safe_pos = True
        self.speaker_two.save()

        self.assertEqual(
            [self.speaker_two.pk, self.speaker_one.pk, self.speaker_three.pk],
            self.speaker_list.current_order(),
        )
        self.speaker_three.safe_pos = True
        self.speaker_three.save()
        self.speaker_list.reorder()
        self.assertEqual(
            [self.speaker_two.pk, self.speaker_three.pk, self.speaker_one.pk],
            self.speaker_list.current_order(),
        )
        self.speaker_two.safe_pos = False
        self.speaker_two.save()
        self.speaker_list.reorder()
        self.assertEqual(
            [self.speaker_three.pk, self.speaker_one.pk, self.speaker_two.pk],
            self.speaker_list.current_order(),
        )

    def test_safe_pos_updated_on_reorder(self):
        self.system.safe_positions = 1
        self.system.active_list = self.speaker_list
        self.system.save()
        self.speaker_list.reorder()
        self.speaker_one.refresh_from_db()
        self.speaker_two.refresh_from_db()
        self.assertTrue(self.speaker_one.safe_pos)
        self.assertFalse(self.speaker_two.safe_pos)

    def test_order_signaled_on_delete(self):
        from voteit.speaker.signals import list_updated
        from voteit.speaker.models import SpeakerList

        L = []

        @receiver(list_updated, sender=SpeakerList)
        def my_listener(instance, queue, **kw):
            L.append(queue)

        self.speaker_two.delete()
        self.assertTrue(L)
        self.assertEqual(
            [self.speaker_one.pk, self.speaker_three.pk], L[0]
        )  # First event

    def test_reoder_invoked_on_delete(self):
        self.speaker_one.created = now()  # Now later than the 3rd speaker
        self.speaker_one.save()
        self.speaker_two.delete()
        self.assertEqual(
            [self.speaker_three.pk, self.speaker_one.pk],
            self.speaker_list.current_order(),
        )

    def test_set_settings_from_schema_directly(self):
        from voteit.speaker.app.list_methods.priority import PrioritySettingsSchema
        from voteit.speaker.app.list_methods.priority import Priority

        self.system.method_name = "priority"
        self.system.method = Priority(self.system)  # Rewrap to clear cache
        self.system.save()
        self.system.refresh_from_db()
        settings = PrioritySettingsSchema(max_times=2)
        self.system.settings = settings
        self.assertEqual(2, self.system.settings.max_times)

    def test_set_settings_without_existing_schema(self):
        with self.assertRaises(ValueError):
            self.system.settings = {}
