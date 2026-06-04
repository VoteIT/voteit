from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.test import TestCase
from django.utils.timezone import now
from rest_framework.exceptions import ValidationError

from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.speaker.app.list_methods.priority import Priority
from voteit.speaker.app.list_methods.priority import PrioritySettingsSchema
from voteit.speaker.app.list_methods.simple import Simple
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.models import SpeakerList
from voteit.speaker.signals import list_method_added
from voteit.speaker.signals import list_method_removed
from voteit.speaker.statemachines import SpeakerSystemStateMachine

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

    def test_start(self):
        speaker = self.list.speaker_items.create(user=self.user)
        speaker.start()
        self.assertIsInstance(speaker.started, datetime)

    def test_ended(self):
        speaker = self.list.speaker_items.create(
            user=self.user, started=now(), seconds=100
        )
        self.assertEqual(timedelta(seconds=100), speaker.ended - speaker.started)

    def test_current(self):
        # This is cheating since we can only expect it to be the current speaker if some data isn't corrupt ;)
        speaker = self.list.speaker_items.create(user=self.user)
        self.assertFalse(speaker.current)
        speaker.start()
        self.assertTrue(speaker.current)
        speaker.stop()
        self.assertFalse(speaker.current)
        self.assertEqual(1, speaker.seconds)

    def test_constraint_only_one_ongoing_speaker(self):
        self.list.speaker_items.create(user=self.user, started=now())
        speaker2 = self.list.speaker_items.create(user=self.user2)
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
        with self.assertRaises(IntegrityError) as cm:
            self.list.speaker_items.create(user=self.user)
        self.assertIn(
            'duplicate key value violates unique constraint "only_unique_users_in_queue"',
            str(cm.exception),
        )

    def test_stop_forgotten_speaker(self):
        speaker = self.list.speaker_items.create(
            user=self.user, started=now() - timedelta(days=999)
        )
        speaker.stop()
        speaker.save()
        self.assertEqual(32767, speaker.seconds)


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
        cls.speaker_list.reorder()

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
        self.speaker_list.order = ""
        self.assertEqual(
            [self.user_two.pk, self.user_three.pk, self.user_one.pk],
            self.speaker_list.reorder(),
        )

    def test_speakers_in_queue_or_speaking(self):
        for _ in range(3):
            self.speaker_list.speaker_items.create(
                user=self.user_one, started=now(), seconds=1
            )
        for _ in range(4):
            self.speaker_list.speaker_items.create(
                user=self.user_two, started=now(), seconds=1
            )
        for _ in range(5):
            self.speaker_list.speaker_items.create(
                user=self.user_three, started=now(), seconds=1
            )
        self.assertEqual(
            {self.user_one.pk, self.user_two.pk, self.user_three.pk},
            {x.user_id for x in self.speaker_list.speakers_in_queue_or_speaking()},
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
        self.speaker_list.order = ""
        self.speaker_list.reorder()

        self.assertTrue(L)
        self.assertEqual(
            [self.user_two.pk, self.user_three.pk, self.user_one.pk], L[0]
        )  # First event

    def test_different_meeting_contexts(self):
        new_meeting = Meeting.objects.create()
        new_ai = new_meeting.agenda_items.create()
        with self.assertRaises(IntegrityError):
            self.system.speaker_lists.create(agenda_item=new_ai)


class SpeakerListSystemsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        room = cls.meeting.rooms.create()
        cls.system = SpeakerListSystem.objects.create(
            method_name="simple",
            state=SpeakerSystemStateMachine.active.value,
            room=room,
        )
        cls.moderator = User.objects.create(username="test_moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)

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
        one_list.speaker_items.create(user=one_user)
        one_list.speaker_items.create(user=one_two, started=now())
        self.system.active_list = one_list
        self.system.save()
        self.system.archive()
        self.assertIsNone(self.system.active_list)
        self.assertTrue(self.system.is_archived)
        one_list.refresh_from_db()
        self.assertEqual([], one_list.order_list)
        self.assertEqual(0, one_list.speaker_items.count())

    def test_inactivating_causes_active_list_to_become_inactive(self):
        slist = self.system.speaker_lists.create()
        self.system.active_list = slist
        self.system.save()
        self.system.inactivate(user=self.moderator)
        self.assertIsNone(self.system.active_list)

    def test_archiving_causes_list_to_clear_order(self):
        slist = self.system.speaker_lists.create(order="1,2,3")
        self.system.active_list = slist
        self.system.archive()
        slist.refresh_from_db()
        self.assertEqual("", slist.order)

    def test_inactivating_with_speaker_causes_error(self):
        user = User.objects.create(username="speaker")
        slist = self.system.speaker_lists.create()
        self.system.active_list = slist
        self.system.save()
        speaker = slist.speaker_items.create(user=user, started=now())
        slist.active_speaker(refresh=True)
        with self.assertRaises(ValidationError):
            self.system.inactivate(user=self.moderator)
        speaker.delete()
        slist.refresh_from_db()
        self.system.inactivate(user=self.moderator)

    def test_adding_method_triggers_add_signal(self):
        self.system.method_name = ""
        self.system.save()
        L = []

        @receiver(list_method_added, sender=Simple)
        def listener(instance, **kw):
            L.append(instance)

        self.system.method_name = Simple.name
        self.system.save()
        self.assertEqual([self.system], L)

    def test_changing_method_triggers_remove_signal(self):
        L = []

        @receiver(list_method_removed, sender=Simple)
        def listener(instance, **kw):
            L.append(instance)

        self.system.method_name = Priority.name
        self.system.save()
        self.assertEqual([self.system], L)

    def test_delete_triggers_remove_signal(self):
        L = []

        @receiver(list_method_removed, sender=Simple)
        def listener(instance, **kw):
            L.append(instance)

        self.system.delete()
        self.assertEqual([self.system], L)

    def test_change_with_bad_name(self):
        self.system.method_name = "broken"
        self.system._initial_method_name = "broken"
        self.system.save_base()
        L = []

        @receiver(list_method_removed)
        def listener(instance, **kw):
            L.append(instance)

        self.system.method_name = Simple.name
        self.system.save()
        # No errors please
        self.assertEqual([], L)


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
