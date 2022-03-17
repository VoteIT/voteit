from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.test import TestCase

from envelope.messages.common import Status
from envelope.messages.errors import BadRequestError
from envelope.messages.errors import NotFoundError
from envelope.messages.errors import UnauthorizedError
from envelope.messages.errors import ValidationErrorMsg


User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SpeakerListEnterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        cls.system = SpeakerListSystem.objects.create(
            method_name="simple", state="active"
        )
        cls.list = SpeakerList.objects.create(speaker_system=cls.system)
        cls.user = User.objects.create(username="jane")
        cls.system.add_roles(cls.user, "speaker")

    @property
    def _cut(self):
        from voteit.speaker.messages import SpeakerListEnter

        return SpeakerListEnter

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.list.pk)
        return self._cut(mm={"user_pk": self.user.pk, "consumer_name": "abc"}, **kw)

    def test_enter(self):
        self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        msg.run_job()
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())

    def test_enter_already_in_list(self):
        self.list.speaker_items.create(user=self.user)
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        self.assertRaises(BadRequestError, msg.run_job)

    def test_enter_closed_list(self):
        self.list.close()
        self.list.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SpeakerListLeaveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.speaker.models import SpeakerListSystem

        cls.system = SpeakerListSystem.objects.create(method_name="simple")
        cls.user = User.objects.create(username="jane")
        cls.system.add_roles(cls.user, "speaker")

    def setUp(self):
        self.list = self.system.speaker_lists.create()
        self.speaker = self.list.speaker_items.create(user=self.user)

    @property
    def _cut(self):
        from voteit.speaker.messages import SpeakerListLeave

        return SpeakerListLeave

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.list.pk)
        return self._cut(mm={"user_pk": self.user.pk, "consumer_name": "abc"}, **kw)

    def test_leave(self):
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        msg.run_job()
        self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())

    def test_leave_not_in_list(self):
        self.speaker.delete()
        self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        self.assertRaises(BadRequestError, msg.run_job)

    def test_leave_with_old_entry(self):
        self.speaker.order = None
        self.speaker.save()
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        self.assertRaises(BadRequestError, msg.run_job)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SpeakerListSetActiveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.speaker.models import SpeakerList
        from voteit.meeting.models import Meeting

        meeting = Meeting.objects.create()
        cls.system = meeting.speaker_systems.create(
            method_name="simple", state="active"
        )
        cls.list = SpeakerList.objects.create(speaker_system=cls.system)
        cls.user = User.objects.create(username="jane")
        cls.system.add_roles(cls.user, "list_moderator")

    @property
    def _cut(self):
        from voteit.speaker.messages import SetActiveList

        return SetActiveList

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.list.pk)
        return self._cut(mm={"user_pk": self.user.pk, "consumer_name": "abc"}, **kw)

    def test_set_active(self):

        msg = self._mk_one()
        response = msg.run_job()
        self.assertIsInstance(response, Status)
        self.system.refresh_from_db()
        self.assertEqual(self.system.active_list, self.list)

    def test_set_active_already_active(self):
        self.system.active_list = self.list
        self.system.save()
        msg = self._mk_one()
        response = msg.run_job()
        self.assertIsNone(response)

    def test_set_active_another_list_has_current_speaker(self):
        other_list = self.system.speaker_lists.create()
        self.system.active_list = other_list
        self.system.save()
        other_speaker = other_list.speaker_items.create(user=self.user)
        other_list.start_speaker(other_speaker)
        msg = self._mk_one()
        self.assertRaises(ValidationErrorMsg, msg.run_job)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class StartSpeakerInListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.speaker.models import SpeakerList
        from voteit.meeting.models import Meeting

        meeting = Meeting.objects.create()
        cls.system = meeting.speaker_systems.create(
            method_name="simple", state="active"
        )
        cls.list = SpeakerList.objects.create(speaker_system=cls.system)
        cls.system.active_list = cls.list
        cls.system.save()
        cls.user = User.objects.create(username="jane")
        cls.speaker = cls.list.speaker_items.create(user=cls.user)
        cls.moderator = User.objects.create(username="moderator")
        cls.system.add_roles(cls.user, "speaker")
        cls.system.add_roles(cls.moderator, "list_moderator")

    @property
    def _cut(self):
        from voteit.speaker.messages import StartSpeakerInList

        return StartSpeakerInList

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.list.pk)
        kw.setdefault("user", self.user.pk)
        return self._cut(
            mm={"user_pk": self.moderator.pk, "consumer_name": "abc"}, **kw
        )

    def test_start_speaker(self):
        self.assertIsNone(self.list.current)
        msg = self._mk_one()
        msg.run_job()
        self.list.refresh_from_db()
        self.assertIsNotNone(self.list.current)
        self.speaker.refresh_from_db()
        self.assertIsInstance(self.speaker.started, datetime)
        self.assertEqual(self.list.current, self.speaker)

    def test_start_speaker_already_started(self):
        self.list.start_speaker(self.speaker)
        self.assertIsNotNone(self.list.current)
        msg = self._mk_one()
        self.assertRaises(ValidationErrorMsg, msg.run_job)

    def test_start_speaker_someone_else_speaking(self):
        new_user = User.objects.create(username="new_speaker")
        new_speaker = self.list.speaker_items.create(user=new_user)
        self.list.start_speaker(new_speaker)
        self.assertEqual(new_speaker, self.list.current)
        msg = self._mk_one()
        msg.run_job()
        self.list.refresh_from_db()
        self.assertEqual(self.speaker, self.list.current)

    def test_start_speaker_not_active_list(self):
        self.system.active_list = None
        self.system.save()
        msg = self._mk_one()
        self.assertRaises(UnauthorizedError, msg.run_job)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class StopSpeakerInListTests(TestCase):
    def setUp(self):
        from voteit.speaker.models import SpeakerList
        from voteit.meeting.models import Meeting

        meeting = Meeting.objects.create()
        self.system = meeting.speaker_systems.create(
            method_name="simple", state="active"
        )
        self.list = SpeakerList.objects.create(speaker_system=self.system)
        self.system.active_list = self.list
        self.system.save()
        self.user = User.objects.create(username="jane")
        self.speaker = self.list.speaker_items.create(user=self.user)
        self.list.start_speaker(self.speaker)
        self.list.refresh_from_db()
        self.moderator = User.objects.create(username="moderator")
        self.system.add_roles(self.user, "speaker")
        self.system.add_roles(self.moderator, "list_moderator")

    @property
    def _cut(self):
        from voteit.speaker.messages import StopSpeakerInList

        return StopSpeakerInList

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.list.pk)
        kw.setdefault("user", self.user.pk)
        return self._cut(
            mm={"user_pk": self.moderator.pk, "consumer_name": "abc"}, **kw
        )

    def test_stop_speaker(self):
        msg = self._mk_one()
        msg.run_job()
        self.list.refresh_from_db()
        self.speaker.refresh_from_db()
        self.assertIsNone(self.list.current)
        self.assertEqual(1, self.speaker.seconds)

    def test_stop_speaker_no_current_speaker(self):
        self.list.stop_speaker()
        msg = self._mk_one()
        self.assertRaises(ValidationErrorMsg, msg.run_job)

    def test_stop_speaker_another_speaker_is_active(self):
        nonspeaking_user = self.list.speakers.create(username="falsy")
        msg = self._mk_one(user=nonspeaking_user.pk)
        self.assertRaises(ValidationErrorMsg, msg.run_job)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class ModeratorSpeakerListEnterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.speaker.models import SpeakerList
        from voteit.speaker.models import SpeakerListSystem
        from voteit.meeting.models import Meeting

        meeting: Meeting = Meeting.objects.create()
        cls.system: SpeakerListSystem = meeting.speaker_systems.create(
            method_name="simple", state="active"
        )
        cls.list: SpeakerList = cls.system.speaker_lists.create()
        cls.user = User.objects.create(username="jane")
        cls.moderator = User.objects.create(username="moderator")
        cls.system.add_roles(cls.user, "speaker")
        cls.system.add_roles(cls.moderator, "list_moderator")

    def setUp(self):
        self.list.refresh_from_db()

    @property
    def _cut(self):
        from voteit.speaker.messages import ModeratorSpeakerListEnter

        return ModeratorSpeakerListEnter

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.list.pk)
        kw.setdefault("user", self.user.pk)
        return self._cut(
            mm={"user_pk": self.moderator.pk, "consumer_name": "abc"}, **kw
        )

    def test_enter(self):
        self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        msg.run_job()
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())

    def test_enter_already_in_list(self):
        self.list.speaker_items.create(user=self.user)
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        self.assertRaises(BadRequestError, msg.run_job)

    def test_enter_closed_list(self):
        self.list.close()
        self.list.save()
        msg = self._mk_one()
        msg.run_job()
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())

    def test_enter_wrong_user(self):
        msg = self._mk_one(user=-1)
        self.assertRaises(NotFoundError, msg.run_job)

    def test_enter_user_not_in_meeting(self):
        outsider = User.objects.create(username="newkid")
        msg = self._mk_one(user=outsider.pk)
        self.assertRaises(BadRequestError, msg.run_job)

    def test_enter_user_already_speaking(self):
        speaker = self.list.speaker_items.create(user=self.user)
        self.list.start_speaker(speaker)
        msg = self._mk_one()
        self.assertRaises(BadRequestError, msg.run_job)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class ModeratorSpeakerListLeaveTests(TestCase):
    def setUp(self):
        from voteit.speaker.models import SpeakerList
        from voteit.meeting.models import Meeting

        meeting = Meeting.objects.create()
        self.system = meeting.speaker_systems.create(
            method_name="simple", state="active"
        )
        self.list = SpeakerList.objects.create(speaker_system=self.system)
        self.user = User.objects.create(username="jane")
        self.system.add_roles(self.user, "speaker")
        self.speaker = self.list.speaker_items.create(user=self.user)
        self.moderator = User.objects.create(username="moderator")
        self.system.add_roles(self.moderator, "list_moderator")

    @property
    def _cut(self):
        from voteit.speaker.messages import ModeratorSpeakerListLeave

        return ModeratorSpeakerListLeave

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.list.pk)
        kw.setdefault("user", self.user.pk)
        return self._cut(
            mm={"user_pk": self.moderator.pk, "consumer_name": "abc"}, **kw
        )

    def test_leave(self):
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        msg.run_job()
        self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())

    def test_leave_not_in_list(self):
        self.speaker.delete()
        self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        self.assertRaises(BadRequestError, msg.run_job)

    def test_leave_with_old_entry(self):
        self.speaker.order = None
        self.speaker.save()
        self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
        msg = self._mk_one()
        self.assertRaises(BadRequestError, msg.run_job)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class ModeratorSpeakerListUndoTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        meeting = Meeting.objects.create()
        user = User.objects.create(username="jane")
        system = meeting.speaker_systems.create(method_name="simple", state="active")
        system.add_roles(user, "speaker")
        self.list = system.speaker_lists.create()
        system.active_list = self.list
        system.save()
        self.speaker = self.list.speaker_items.create(user=user)
        self.list.start_speaker(self.speaker)
        self.moderator = User.objects.create(username="moderator")
        system.add_roles(self.moderator, "list_moderator")

    @property
    def _cut(self):
        from voteit.speaker.messages import ModeratorSpeakerListUndo

        return ModeratorSpeakerListUndo

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.list.pk)
        return self._cut(
            mm={"user_pk": self.moderator.pk, "consumer_name": "abc"}, **kw
        )

    def test_undo(self):
        self.assertEqual(self.list.current, self.speaker)
        msg = self._mk_one()
        response = msg.run_job()
        self.list.refresh_from_db()
        self.assertIs(self.list.current, None)

    def test_undo_no_active_speaker(self):
        self.list.stop_speaker()
        self.assertFalse(self.list.current)
        msg = self._mk_one()
        self.assertRaises(BadRequestError, msg.run_job)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SpeakerListShuffleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        cls.system: SpeakerListSystem = SpeakerListSystem.objects.create(
            method_name="simple", state="active"
        )
        cls.moderator = User.objects.create(username="moderator")
        cls.system.add_roles(cls.moderator, "list_moderator")
        cls.list: SpeakerList = SpeakerList.objects.create(speaker_system=cls.system)
        for i in range(10):
            user = cls.list.speakers.create(username=f"user-{i}")
            cls.list.speaker_items.create(user=user, order=i)

    @property
    def _cut(self):
        from voteit.speaker.messages import ModeratorSpeakerListShuffle

        return ModeratorSpeakerListShuffle

    def _mk_one(self, **kw):
        kw.setdefault("pk", self.list.pk)
        return self._cut(
            mm={"user_pk": self.moderator.pk, "consumer_name": "abc"}, **kw
        )

    def test_shuffle_causes_new_order(self):
        current_order = self.list.current_order()
        self.assertEqual(10, len(current_order))
        msg = self._mk_one()
        order_changed = False
        for i in range(5):
            msg.run_job()
            if current_order != self.list.current_order():
                order_changed = True
                break

        self.assertTrue(order_changed)
