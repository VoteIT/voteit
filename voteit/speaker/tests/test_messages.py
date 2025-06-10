from datetime import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.test import TestCase
from django.utils.timezone import now
from envelope.channels.errors import SubscribeError
from envelope.channels.messages import Subscribe
from envelope.channels.messages import Subscribed
from envelope.messages.common import Status
from envelope.messages.errors import BadRequestError
from envelope.messages.errors import NotFoundError
from envelope.messages.errors import UnauthorizedError
from envelope.messages.errors import ValidationErrorMsg
from envelope.testing import MessageCatcher
from envelope.testing import testing_channel_layers_setting

from voteit.core.testing import FakeCommit

from voteit.meeting.models import Meeting
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.roles import ROLE_LIST_MODERATOR
from voteit.speaker.roles import ROLE_SPEAKER
from voteit.speaker.workflows import SpeakerListWf
from voteit.speaker.workflows import SpeakerSystemWf

User = get_user_model()

# @override_settings(CHANNEL_LAYERS=_channel_layers_setting)
# class SpeakerListSystemChannelSubscribeTests(TestCase):
#     fixtures = ["meeting_test_fixture"]
#
#     @classmethod
#     def setUpTestData(cls):
#         cls.participant = User.objects.get(username="participant")
#         cls.outsider = User.objects.create(username="outsider")
#         cls.meeting = Meeting.objects.get(pk=1)
#         cls.room = cls.meeting.rooms.create()
#         cls.system: SpeakerListSystem = SpeakerListSystem.objects.create(
#             method_name="simple", room=cls.room
#         )
#
#     def _mk_msg(self, user):
#         return Subscribe(
#             mm={"consumer_name": "abc", "user_pk": user.pk},
#             pk=self.system.pk,
#             channel_type=SpeakerListSystemChannel.name,
#         )
#
#     def test_subscribe(self):
#         msg = self._mk_msg(self.participant)
#         with MessageCatcher(Subscribed) as messages:
#             msg.run_job()
#         self.assertEqual(1, len(messages))
#         response = messages[0]
#         self.assertIsInstance(response, Subscribed)
#
#     def test_subscribe_outsider(self):
#         msg = self._mk_msg(self.outsider)
#         with self.assertRaises(SubscribeError):
#             msg.run_job()


# @override_settings(CHANNEL_LAYERS=_channel_layers_setting)
# class SpeakerListEnterTests(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         meeting = Meeting.objects.create()
#         room = meeting.rooms.create()
#         cls.system: SpeakerListSystem = SpeakerListSystem.objects.create(
#             method_name="simple",
#             state=SpeakerSystemWf.ACTIVE,
#             room=room,
#         )
#         cls.list: SpeakerList = SpeakerList.objects.create(speaker_system=cls.system)
#         cls.user = User.objects.create(username="jane")
#         cls.system.add_roles(cls.user, ROLE_SPEAKER)
#
#     @property
#     def _cut(self):
#         from voteit.speaker.messages import SpeakerListEnter
#
#         return SpeakerListEnter
#
#     def _mk_one(self, **kw):
#         kw.setdefault("pk", self.list.pk)
#         return self._cut(mm={"user_pk": self.user.pk, "consumer_name": "abc"}, **kw)
#
#     def test_enter(self):
#         self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())
#         msg = self._mk_one()
#         msg.run_job()
#         self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
#
#     def test_enter_already_in_list(self):
#         self.list.speaker_items.create(user=self.user)
#         self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
#         msg = self._mk_one()
#         self.assertRaises(BadRequestError, msg.run_job)
#
#     def test_enter_closed_list(self):
#         self.list.close()
#         self.list.save()
#         msg = self._mk_one()
#         self.assertRaises(UnauthorizedError, msg.run_job)


# @override_settings(CHANNEL_LAYERS=_channel_layers_setting)
# class SpeakerListLeaveTests(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         meeting = Meeting.objects.create()
#         room = meeting.rooms.create()
#         cls.system: SpeakerListSystem = SpeakerListSystem.objects.create(
#             method_name="simple", room=room
#         )
#         cls.user = User.objects.create(username="jane")
#         cls.system.add_roles(cls.user, ROLE_SPEAKER)
#
#     def setUp(self):
#         self.list = self.system.speaker_lists.create()
#         self.speaker = self.list.speaker_items.create(user=self.user)
#
#     @property
#     def _cut(self):
#         from voteit.speaker.messages import SpeakerListLeave
#
#         return SpeakerListLeave
#
#     def _mk_one(self, **kw):
#         kw.setdefault("pk", self.list.pk)
#         return self._cut(mm={"user_pk": self.user.pk, "consumer_name": "abc"}, **kw)
#
#     def test_leave(self):
#         self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
#         msg = self._mk_one()
#         msg.run_job()
#         self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())
#
#     def test_leave_not_in_list(self):
#         self.speaker.delete()
#         self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())
#         msg = self._mk_one()
#         self.assertRaises(BadRequestError, msg.run_job)
#
#     def test_leave_with_old_entry(self):
#         self.speaker.seconds = 10
#         self.speaker.started = now()
#         self.speaker.save()
#         self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
#         msg = self._mk_one()
#         self.assertRaises(BadRequestError, msg.run_job)


# @override_settings(CHANNEL_LAYERS=_channel_layers_setting)
# class SpeakerListSetActiveTests(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         meeting: Meeting = Meeting.objects.create()
#         room = meeting.rooms.create()
#         cls.system = meeting.speaker_systems.create(
#             method_name="simple", state=SpeakerSystemWf.ACTIVE, room=room
#         )
#         cls.list: SpeakerList = SpeakerList.objects.create(speaker_system=cls.system)
#         cls.user = User.objects.create(username="jane")
#         cls.system.add_roles(cls.user, ROLE_LIST_MODERATOR)
#
#     @property
#     def _cut(self):
#         from voteit.speaker.messages import SetActiveList
#
#         return SetActiveList
#
#     def _mk_one(self, **kw):
#         kw.setdefault("pk", self.list.pk)
#         return self._cut(mm={"user_pk": self.user.pk, "consumer_name": "abc"}, **kw)
#
#     def test_set_active(self):
#         msg = self._mk_one()
#         response = msg.run_job()
#         self.assertIsInstance(response, Status)
#         self.system.refresh_from_db()
#         self.assertEqual(self.system.active_list, self.list)
#
#     def test_set_active_already_active(self):
#         self.system.active_list = self.list
#         self.system.save()
#         msg = self._mk_one()
#         response = msg.run_job()
#         self.assertIsNone(response)
#
#     def test_set_active_another_list_has_current_speaker(self):
#         other_list = self.system.speaker_lists.create()
#         self.system.active_list = other_list
#         self.system.save()
#         other_speaker = other_list.speaker_items.create(user=self.user)
#         other_list.start_speaker(other_speaker)
#         msg = self._mk_one()
#         self.assertRaises(ValidationErrorMsg, msg.run_job)


# @override_settings(CHANNEL_LAYERS=_channel_layers_setting)
# class DeactivateListTests(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         meeting: Meeting = Meeting.objects.create()
#         cls.room = meeting.rooms.create()
#         cls.system = meeting.speaker_systems.create(
#             method_name="simple", state=SpeakerSystemWf.ACTIVE, room=cls.room
#         )
#         cls.list: SpeakerList = SpeakerList.objects.create(speaker_system=cls.system)
#         cls.user = User.objects.create(username="jane")
#         cls.system.add_roles(cls.user, ROLE_LIST_MODERATOR)
#         cls.system.active_list = cls.list
#         cls.system.save()
#
#     @property
#     def _cut(self):
#         from voteit.speaker.messages import DeactivateList
#
#         return DeactivateList
#
#     def _mk_one(self, **kw):
#         kw.setdefault("pk", self.list.pk)
#         return self._cut(mm={"user_pk": self.user.pk, "consumer_name": "abc"}, **kw)
#
#     def test_deactivate(self):
#         msg = self._mk_one()
#         response = msg.run_job()
#         self.assertIsInstance(response, Status)
#         self.system.refresh_from_db()
#         self.assertEqual(self.system.active_list, None)
#         self.list.refresh_from_db()
#         self.assertFalse(self.list.is_active_list)
#
#     def test_deactivate_with_active_speaker(self):
#         speaker = self.list.speaker_items.create(user=self.user)
#         self.list.start_speaker(speaker)
#         msg = self._mk_one()
#         with self.assertRaises(ValidationErrorMsg):
#             msg.run_job()
#
#     def test_deactivate_and_close_list(self):
#         msg = self._mk_one(close_list=True)
#         msg.run_job()
#         self.list.refresh_from_db()
#         self.assertEqual(SpeakerListWf.CLOSED, self.list.state)
#         self.assertFalse(self.list.is_active_list)


# @override_settings(CHANNEL_LAYERS=_channel_layers_setting)
# class StartSpeakerInListTests(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         meeting: Meeting = Meeting.objects.create()
#         room = meeting.rooms.create()
#         cls.system: SpeakerListSystem = meeting.speaker_systems.create(
#             method_name="simple", state=SpeakerSystemWf.ACTIVE, room=room
#         )
#         cls.list = SpeakerList.objects.create(speaker_system=cls.system)
#         cls.system.active_list = cls.list
#         cls.system.save()
#         cls.user = User.objects.create(username="jane")
#         cls.speaker = cls.list.speaker_items.create(user=cls.user)
#         cls.moderator = User.objects.create(username="moderator")
#         cls.system.add_roles(cls.user, ROLE_SPEAKER)
#         cls.system.add_roles(cls.moderator, ROLE_LIST_MODERATOR)
#
#     @property
#     def _cut(self):
#         from voteit.speaker.messages import StartSpeakerInList
#
#         return StartSpeakerInList
#
#     def _mk_one(self, **kw):
#         kw.setdefault("pk", self.list.pk)
#         kw.setdefault("user", self.user.pk)
#         return self._cut(
#             mm={"user_pk": self.moderator.pk, "consumer_name": "abc"}, **kw
#         )
#
#     def test_start_speaker(self):
#         self.assertIsNone(self.list.current)
#         msg = self._mk_one()
#         msg.run_job()
#         self.list.refresh_from_db()
#         self.assertIsNotNone(self.list.current)
#         self.speaker.refresh_from_db()
#         self.assertIsInstance(self.speaker.started, datetime)
#         self.assertEqual(self.list.current, self.speaker)
#
#     def test_start_speaker_already_started(self):
#         self.list.start_speaker(self.speaker)
#         self.assertIsNotNone(self.list.current)
#         msg = self._mk_one()
#         self.assertRaises(ValidationErrorMsg, msg.run_job)
#
#     def test_start_speaker_someone_else_speaking(self):
#         new_user = User.objects.create(username="new_speaker")
#         new_speaker = self.list.speaker_items.create(user=new_user)
#         self.list.start_speaker(new_speaker)
#         self.assertEqual(new_speaker, self.list.current)
#         msg = self._mk_one()
#         msg.run_job()
#         self.list.refresh_from_db()
#         self.assertEqual(self.speaker, self.list.current)
#
#     def test_start_speaker_not_active_list(self):
#         self.system.active_list = None
#         self.system.save()
#         msg = self._mk_one()
#         self.assertRaises(UnauthorizedError, msg.run_job)


# @override_settings(CHANNEL_LAYERS=_channel_layers_setting)
# class StopSpeakerInListTests(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         meeting: Meeting = Meeting.objects.create()
#         room = meeting.rooms.create()
#         cls.system: SpeakerListSystem = meeting.speaker_systems.create(
#             method_name="simple", state=SpeakerSystemWf.ACTIVE, room=room
#         )
#         cls.list = SpeakerList.objects.create(speaker_system=cls.system)
#         cls.system.active_list = cls.list
#         cls.system.save()
#         cls.user = User.objects.create(username="jane")
#         cls.speaker = cls.list.speaker_items.create(user=cls.user)
#         cls.list.start_speaker(cls.speaker)
#         cls.list.refresh_from_db()
#         cls.moderator = User.objects.create(username="moderator")
#         cls.system.add_roles(cls.user, ROLE_SPEAKER)
#         cls.system.add_roles(cls.moderator, ROLE_LIST_MODERATOR)
#
#     @property
#     def _cut(self):
#         from voteit.speaker.messages import StopSpeakerInList
#
#         return StopSpeakerInList
#
#     def _mk_one(self, **kw):
#         kw.setdefault("pk", self.list.pk)
#         kw.setdefault("user", self.user.pk)
#         return self._cut(
#             mm={"user_pk": self.moderator.pk, "consumer_name": "abc"}, **kw
#         )
#
#     def test_stop_speaker(self):
#         msg = self._mk_one()
#         msg.run_job()
#         self.list.refresh_from_db()
#         self.speaker.refresh_from_db()
#         self.assertIsNone(self.list.current)
#         self.assertEqual(1, self.speaker.seconds)
#
#     def test_stop_speaker_no_current_speaker_with_bogus_data(self):
#         self.list.stop_speaker()
#         self.speaker.started = now()
#         self.assertIsNone(self.speaker.seconds)
#         msg = self._mk_one()
#         # No longer failing
#         msg.run_job()
#         self.speaker.refresh_from_db()
#         self.assertEqual(1, self.speaker.seconds)


# @override_settings(CHANNEL_LAYERS=_channel_layers_setting)
# class ModeratorSpeakerListEnterTests(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         meeting: Meeting = Meeting.objects.create()
#         cls.room = meeting.rooms.create()
#         cls.system: SpeakerListSystem = meeting.speaker_systems.create(
#             method_name="simple",
#             state=SpeakerSystemWf.ACTIVE,
#             room=cls.room,
#         )
#         cls.list: SpeakerList = cls.system.speaker_lists.create()
#         cls.user = User.objects.create(username="jane")
#         cls.moderator = User.objects.create(username="moderator")
#         cls.system.add_roles(cls.user, ROLE_SPEAKER)
#         cls.system.add_roles(cls.moderator, ROLE_LIST_MODERATOR)
#
#     def setUp(self):
#         self.list.refresh_from_db()
#
#     @property
#     def _cut(self):
#         from voteit.speaker.messages import ModeratorSpeakerListEnter
#
#         return ModeratorSpeakerListEnter
#
#     def _mk_one(self, **kw):
#         kw.setdefault("pk", self.list.pk)
#         kw.setdefault("user", self.user.pk)
#         return self._cut(
#             mm={"user_pk": self.moderator.pk, "consumer_name": "abc"}, **kw
#         )
#
#     def test_enter(self):
#         self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())
#         msg = self._mk_one()
#         msg.run_job()
#         self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
#
#     def test_enter_already_in_list(self):
#         self.list.speaker_items.create(user=self.user)
#         self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
#         msg = self._mk_one()
#         self.assertRaises(BadRequestError, msg.run_job)
#
#     def test_enter_closed_list(self):
#         self.list.close()
#         self.list.save()
#         msg = self._mk_one()
#         msg.run_job()
#         self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
#
#     def test_enter_wrong_user(self):
#         msg = self._mk_one(user=-1)
#         self.assertRaises(NotFoundError, msg.run_job)
#
#     def test_enter_user_not_in_meeting(self):
#         outsider = User.objects.create(username="newkid")
#         msg = self._mk_one(user=outsider.pk)
#         self.assertRaises(BadRequestError, msg.run_job)
#
#     def test_enter_user_already_speaking(self):
#         speaker = self.list.speaker_items.create(user=self.user)
#         self.list.start_speaker(speaker)
#         msg = self._mk_one()
#         self.assertRaises(BadRequestError, msg.run_job)


# @override_settings(CHANNEL_LAYERS=_channel_layers_setting)
# class ModeratorSpeakerListLeaveTests(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         meeting: Meeting = Meeting.objects.create()
#         cls.room = meeting.rooms.create()
#         cls.system: SpeakerListSystem = meeting.speaker_systems.create(
#             method_name="simple", state=SpeakerSystemWf.ACTIVE, room=cls.room
#         )
#         cls.list: SpeakerList = SpeakerList.objects.create(speaker_system=cls.system)
#         cls.user = User.objects.create(username="jane")
#         cls.system.add_roles(cls.user, "speaker")
#         cls.speaker = cls.list.speaker_items.create(user=cls.user)
#         cls.moderator = User.objects.create(username="moderator")
#         cls.system.add_roles(cls.moderator, ROLE_LIST_MODERATOR)
#
#     @property
#     def _cut(self):
#         from voteit.speaker.messages import ModeratorSpeakerListLeave
#
#         return ModeratorSpeakerListLeave
#
#     def _mk_one(self, **kw):
#         kw.setdefault("pk", self.list.pk)
#         kw.setdefault("user", self.user.pk)
#         return self._cut(
#             mm={"user_pk": self.moderator.pk, "consumer_name": "abc"}, **kw
#         )
#
#     def test_leave(self):
#         self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
#         msg = self._mk_one()
#         msg.run_job()
#         self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())
#
#     def test_leave_not_in_list(self):
#         self.speaker.delete()
#         self.assertFalse(self.list.speakers.filter(pk=self.user.pk).exists())
#         msg = self._mk_one()
#         self.assertRaises(BadRequestError, msg.run_job)
#
#     def test_leave_with_old_entry(self):
#         self.speaker.seconds = 10
#         self.speaker.started = now()
#         self.speaker.save()
#         self.assertTrue(self.list.speakers.filter(pk=self.user.pk).exists())
#         msg = self._mk_one()
#         self.assertRaises(BadRequestError, msg.run_job)


# @override_settings(CHANNEL_LAYERS=_channel_layers_setting)
# class ModeratorSpeakerListUndoTests(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         meeting = Meeting.objects.create()
#         user = User.objects.create(username="jane")
#         room = meeting.rooms.create()
#         system = meeting.speaker_systems.create(
#             method_name="simple", state=SpeakerSystemWf.ACTIVE, room=room
#         )
#         system.add_roles(user, "speaker")
#         cls.list = system.speaker_lists.create()
#         system.active_list = cls.list
#         system.save()
#         cls.speaker = cls.list.speaker_items.create(user=user)
#         cls.list.start_speaker(cls.speaker)
#         cls.moderator = User.objects.create(username="moderator")
#         system.add_roles(cls.moderator, ROLE_LIST_MODERATOR)
#
#     @property
#     def _cut(self):
#         from voteit.speaker.messages import ModeratorSpeakerListUndo
#
#         return ModeratorSpeakerListUndo
#
#     def _mk_one(self, **kw):
#         kw.setdefault("pk", self.list.pk)
#         return self._cut(
#             mm={"user_pk": self.moderator.pk, "consumer_name": "abc"}, **kw
#         )
#
#     def test_undo(self):
#         self.assertEqual(self.list.current, self.speaker)
#         msg = self._mk_one()
#         msg.run_job()
#         self.list.refresh_from_db()
#         self.assertIs(self.list.current, None)
#
#     def test_undo_no_active_speaker(self):
#         self.list.stop_speaker()
#         self.assertFalse(self.list.current)
#         msg = self._mk_one()
#         msg.run_job()
#         # This shouldn't fail anylonger
#
#     @patch.object(SpeakerListSystemChannel, "sync_publish")
#     def test_undo_received_messages(self, mock_publish):
#         from voteit.speaker.messages import SpeakerListChanged
#         from voteit.speaker.messages import SpeakerChanged
#
#         self.assertEqual(self.list.current, self.speaker)
#         msg = self._mk_one()
#         with FakeCommit():
#             msg.run_job()
#         messages = [x.args[0] for x in mock_publish.mock_calls]
#         self.assertEqual(2, len(messages))
#         self.assertIsInstance(messages[0], SpeakerListChanged)
#         self.assertIsInstance(messages[1], SpeakerChanged)


# @override_settings(CHANNEL_LAYERS=_channel_layers_setting)
# class SpeakerListShuffleTests(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         meeting = Meeting.objects.create()
#         room = meeting.rooms.create()
#         cls.system: SpeakerListSystem = SpeakerListSystem.objects.create(
#             method_name="simple", state=SpeakerSystemWf.ACTIVE, room=room
#         )
#         cls.moderator = User.objects.create(username="moderator")
#         cls.system.add_roles(cls.moderator, ROLE_LIST_MODERATOR)
#         cls.list: SpeakerList = SpeakerList.objects.create(speaker_system=cls.system)
#         for i in range(10):
#             user = cls.list.speakers.create(username=f"user-{i}")
#
#     @property
#     def _cut(self):
#         from voteit.speaker.messages import ModeratorSpeakerListShuffle
#
#         return ModeratorSpeakerListShuffle
#
#     def _mk_one(self, **kw):
#         kw.setdefault("pk", self.list.pk)
#         return self._cut(
#             mm={"user_pk": self.moderator.pk, "consumer_name": "abc"}, **kw
#         )
#
#     def test_shuffle_causes_new_order(self):
#         order_list = self.list.order_list
#         self.assertEqual(10, len(order_list))
#         msg = self._mk_one()
#         order_changed = False
#         for i in range(5):
#             msg.run_job()
#             if order_list != msg.context.order_list:
#                 order_changed = True
#                 break
#         self.assertTrue(order_changed)
