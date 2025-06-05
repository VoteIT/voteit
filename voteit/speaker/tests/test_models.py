from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.test import TestCase
from django.utils.timezone import now
from django_fsm import TransitionNotAllowed

from voteit.meeting.models import Meeting
from voteit.speaker.app.list_methods.priority import Priority
from voteit.speaker.app.list_methods.priority import PrioritySettingsSchema
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.models import SpeakerList
from voteit.speaker.workflows import SpeakerSystemWf

User = get_user_model()


class SpeakerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        meeting = Meeting.objects.create()
        room = meeting.rooms.create()
        cls.system = SpeakerListSystem.objects.create(method_name="simple", room=room)
        cls.list = SpeakerList.objects.create(speaker_system=cls.system)
        cls.user = User.objects.create(username="jane")
        cls.user2 = User.objects.create(username="doe")

    def test_create_sets_order(self):
        user_one = User.objects.create(username="one")
        user_two = User.objects.create(username="two")
        self.list.speaker_items.create(user=user_one)
        self.list.speaker_items.create(user=user_two)
        self.assertEqual([user_one.pk, user_two.pk], self.list.order_list)

    def test_start(self):
        speaker = self.list.speaker_items.create(user=self.user)
        self.list.start_speaker(speaker)
        self.assertIsInstance(speaker.started, datetime)

    def test_start_with_another_speaker_active(self):
        speaker = self.list.speaker_items.create(user=self.user)
        self.list.start_speaker(speaker)
        tarzan = User.objects.create(username="tarzan")
        tarzan_speaker = self.list.speaker_items.create(user=tarzan)
        self.list.start_speaker(tarzan_speaker)
        speaker.refresh_from_db()
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

    def test_constraint_only_one_ongoing_speaker(self):
        speaker = self.list.speaker_items.create(user=self.user)
        speaker2 = self.list.speaker_items.create(user=self.user2)
        self.list.start_speaker(speaker)
        with self.assertRaises(IntegrityError) as cm:
            speaker2.started = now()
            speaker2.save()
        self.assertIn(
            'duplicate key value violates unique constraint "only_one_ongoing_speaker"',
            str(cm.exception),
        )

    def test_constraint_only_unique_users_in_queue(self):
        speaker = self.list.speaker_items.create(user=self.user)
        self.assertFalse(speaker.current)
        # self.list.start_speaker(speaker)
        with self.assertRaises(IntegrityError) as cm:
            self.list.speaker_items.create(user=self.user)
        self.assertIn(
            'duplicate key value violates unique constraint "only_unique_users_in_queue"',
            str(cm.exception),
        )


class SpeakerListTests(TestCase):
    """
    Lists don't work without a method, so these basics should be tested
    with a bare minimal implementation.
    """

    @classmethod
    def setUpTestData(cls):
        meeting = Meeting.objects.create()
        cls.room = meeting.rooms.create()
        cls.system: SpeakerListSystem = SpeakerListSystem.objects.create(
            method_name="simple", room=cls.room
        )
        cls.speaker_list: SpeakerList = SpeakerList.objects.create(
            speaker_system=cls.system
        )
        cls.user_one = User.objects.create(username="one")
        cls.user_two = User.objects.create(username="two")
        cls.user_three = User.objects.create(username="three")
        cls.speaker_one: Speaker = cls.speaker_list.speaker_items.create(
            user=cls.user_one
        )
        cls.speaker_two: Speaker = cls.speaker_list.speaker_items.create(
            user=cls.user_two
        )
        cls.speaker_three: Speaker = cls.speaker_list.speaker_items.create(
            user=cls.user_three
        )

    def test_order_list(self):
        self.assertEqual(
            [self.user_one.pk, self.user_two.pk, self.user_three.pk],
            self.speaker_list.order_list,
        )

    def test_reorder(self):
        self.assertEqual(
            [self.user_one.pk, self.user_two.pk, self.user_three.pk],
            self.speaker_list.reorder(),
        )
        # Change timestamp...
        self.speaker_one.created = now()
        self.speaker_one.save()
        self.assertEqual(
            [self.user_two.pk, self.user_three.pk, self.user_one.pk],
            self.speaker_list.reorder(),
        )

    def test_reorder_signals_on_change(self):
        L = []

        @receiver(post_save, sender=SpeakerList)
        def my_listener(instance, **kw):
            L.append(instance.order_list)

        self.speaker_list.reorder()
        # No change
        self.assertFalse(L)
        # Changing the order will send event
        self.speaker_one.created = now()
        self.speaker_one.save()
        self.speaker_list.reorder()

        self.assertTrue(L)
        self.assertEqual(
            [self.user_two.pk, self.user_three.pk, self.user_one.pk], L[0]
        )  # First event

    def test_different_meeting_contexts(self):
        new_meeting = Meeting.objects.create()
        new_ai = new_meeting.agenda_items.create()
        self.speaker_list.agenda_item = new_ai
        self.assertRaises(IntegrityError, self.speaker_list.save)

    def test_undo(self):
        self.speaker_list.start_speaker(self.speaker_two)
        self.assertEqual(
            [self.user_one.pk, self.user_three.pk],
            self.speaker_list.order_list,
        )
        self.speaker_list.undo_speaker()
        self.assertEqual(
            [self.user_one.pk, self.user_two.pk, self.user_three.pk],
            self.speaker_list.order_list,
        )

    def test_stop(self):
        self.speaker_list.start_speaker(self.speaker_two)
        self.speaker_two.started = now() - timedelta(minutes=1)
        self.speaker_list.stop_speaker()
        self.speaker_two.refresh_from_db()
        self.assertIsNotNone(self.speaker_two.seconds)

    def test_stop_forgotten_speaker(self):
        self.speaker_list.start_speaker(self.speaker_two)
        self.assertEqual(
            [self.user_one.pk, self.user_three.pk],
            self.speaker_list.order_list,
        )
        self.speaker_list.current.started = now() - timedelta(days=999)
        self.speaker_list.current.save()
        self.speaker_list.stop_speaker()
        self.speaker_two.refresh_from_db()
        self.assertEqual(32767, self.speaker_two.seconds)


class SpeakerListSystemsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        room = cls.meeting.rooms.create()
        cls.system = SpeakerListSystem.objects.create(
            method_name="simple", state=SpeakerSystemWf.ACTIVE, room=room
        )

    def test_set_settings_from_schema_directly(self):
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
        one_list.refresh_from_db()
        self.assertEqual([], one_list.order_list)  # two was deleted
        speaker_one.refresh_from_db()
        self.assertEqual(1, speaker_one.seconds)
        self.assertFalse(speaker_one.in_queue)

    def test_set_active_that_belongs_to_other_system(self):
        room = self.meeting.rooms.create()
        other_sys = SpeakerListSystem.objects.create(
            method_name="simple", state=SpeakerSystemWf.ACTIVE, room=room
        )
        other_list = other_sys.speaker_lists.create()
        self.system.active_list = other_list
        self.assertRaises(IntegrityError, self.system.save)

    def test_inactivating_causes_active_list_to_become_inactive(self):
        slist = self.system.speaker_lists.create()
        self.system.active_list = slist
        self.system.inactivate()
        self.assertIsNone(self.system.active_list)

    def test_inactivating_with_speaker_causes_error(self):
        user = User.objects.create(username="speaker")
        slist = self.system.speaker_lists.create()
        self.system.active_list = slist
        speaker = slist.speaker_items.create(user=user)
        slist.current = speaker
        slist.save()
        with self.assertRaises(TransitionNotAllowed):
            self.system.inactivate()


class DeletingMeetingTests(TestCase):
    """
    Deleting the whole meeting must not cause exceptions
    """

    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.room = cls.meeting.rooms.create()
        ai = cls.meeting.agenda_items.create(title="ai one")
        system: SpeakerListSystem = cls.meeting.speaker_systems.create(
            method_name=Priority.name, room=cls.room
        )
        sl: SpeakerList = system.speaker_lists.create(title="One list", agenda_item=ai)
        moderator = User.objects.get(username="moderator")
        participant = User.objects.get(username="participant")
        sl.speaker_items.create(user=moderator)
        sl.speaker_items.create(user=participant)

    def test_delete(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.meeting.delete()
