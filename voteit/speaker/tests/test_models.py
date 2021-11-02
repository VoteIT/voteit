from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.dispatch import receiver
from django.test import TestCase
from django.utils.timezone import now

User = get_user_model()


class SpeakerTests(TestCase):
    def setUp(self):
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        self.system = SpeakerListSystem.objects.create(method_name="simple")
        self.list = SpeakerList.objects.create(speaker_system=self.system)
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
        self.list.start_speaker(speaker)
        self.assertIsNone(speaker.order)
        self.assertIsInstance(speaker.started, datetime)

    def test_start_with_another_speaker_active(self):
        speaker = self.list.speaker_items.create(user=self.user)
        self.list.start_speaker(speaker)
        tarzan = User.objects.create(username="tarzan")
        tarzan_speaker = self.list.speaker_items.create(user=tarzan)
        self.list.start_speaker(tarzan_speaker)
        self.assertEqual(1, speaker.seconds)
        self.assertEqual(tarzan_speaker, self.list.current)

    def test_ended(self):
        speaker = self.list.speaker_items.create(user=self.user)
        self.list.start_speaker(speaker)
        speaker.seconds = 100
        self.assertEqual(timedelta(seconds=100), speaker.ended - speaker.started)

    def test_current(self):
        # This is cheating since we can only expect it to be the current speaker if some data isn't corrupt ;)
        speaker = self.list.speaker_items.create(user=self.user)
        self.assertFalse(speaker.current)
        self.list.start_speaker(speaker)
        self.assertTrue(speaker.current)
        speaker.seconds = 1
        self.assertFalse(speaker.current)


class SpeakerListTests(TestCase):
    """Lists don't work without a method, so these basics should be tested
    with a bare minimal implementation.
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
        cls.user_one = User.objects.create(username="one")
        cls.user_two = User.objects.create(username="two")
        cls.user_three = User.objects.create(username="three")
        cls.speaker_one = cls.speaker_list.speaker_items.create(user=cls.user_one)
        cls.speaker_two = cls.speaker_list.speaker_items.create(user=cls.user_two)
        cls.speaker_three = cls.speaker_list.speaker_items.create(user=cls.user_three)

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
        def my_listener(instance, **kw):
            L.append(instance.current_order())

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
        def my_listener(instance, **kw):
            L.append(instance.current_order())

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

    def test_different_meeting_contexts(self):
        from voteit.meeting.models import Meeting

        new_meeting = Meeting.objects.create()
        new_ai = new_meeting.agenda_items.create()
        self.speaker_list.agenda_item = new_ai
        self.assertRaises(IntegrityError, self.speaker_list.save)

    def test_undo(self):
        self.speaker_list.start_speaker(self.speaker_two)
        self.assertEqual(
            [self.speaker_one.pk, self.speaker_three.pk],
            self.speaker_list.current_order(),
        )
        self.speaker_list.undo_speaker()
        self.assertEqual(
            [self.speaker_one.pk, self.speaker_two.pk, self.speaker_three.pk],
            self.speaker_list.current_order(),
        )


class SpeakerListSystemsTests(TestCase):
    def setUp(self):
        from voteit.speaker.models import SpeakerListSystem

        self.system = SpeakerListSystem.objects.create(
            method_name="simple", state="active"
        )

    def test_set_settings_from_schema_directly(self):
        from voteit.speaker.app.list_methods.priority import PrioritySettingsSchema

        self.system.method_name = "priority"
        self.system.save()
        self.system.settings = PrioritySettingsSchema(max_times=2)
        self.assertEqual(2, self.system.settings.max_times)

    def test_set_settings_without_existing_schema(self):
        with self.assertRaises(ValueError):
            self.system.settings = {}

    def test_archive(self):
        one_user = User.objects.create(username="one")
        one_two = User.objects.create(username="two")
        one_list = self.system.speaker_lists.create()
        speaker_one = one_list.speaker_items.create(user=one_user)
        speaker_two = one_list.speaker_items.create(user=one_two)
        one_list.start_speaker(speaker_one)
        self.system.active_list = one_list
        self.system.save()
        self.system.archive()
        self.assertIsNone(self.system.active_list)
        self.assertTrue(self.system.is_archived)
        self.assertEqual([], one_list.current_order())  # two was deleted
        speaker_one.refresh_from_db()
        self.assertEqual(1, speaker_one.seconds)
        self.assertFalse(speaker_one.in_queue)
