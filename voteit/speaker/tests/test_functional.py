# from datetime import UTC
# from datetime import datetime
# from unittest.mock import patch
#
# from django.contrib.auth import get_user_model
# from django.test import TestCase
# from django.test import override_settings
# from envelope.channels.models import ContextChannel
#
# from voteit.meeting.models import Meeting
# from voteit.meeting.roles import ROLE_PARTICIPANT
# from voteit.speaker.app.list_methods.priority import Priority
# from voteit.speaker.messages import ModeratorSpeakerListLeave
# from voteit.speaker.messages import SpeakerListEnter
# from voteit.speaker.messages import SpeakerListLeave
# from voteit.speaker.models import SpeakerList
# from voteit.speaker.models import SpeakerListSystem
#
# User = get_user_model()
# _channel_layers_setting = {
#     "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
# }
#
#
# @override_settings(CHANNEL_LAYERS=_channel_layers_setting)
# class SpeakerListFunctionalTests(TestCase):
#     """
#     Some more complex testcases for things that might appear during normal operation.
#     """
#
#     fixtures = ["meeting_test_fixture"]
#
#     @classmethod
#     def setUpTestData(cls):
#         cls.meeting: Meeting = Meeting.objects.get(pk=1)
#         cls.moderator = User.objects.get(username="moderator")
#         cls.user_one = User.objects.create(username="one")
#         cls.user_two = User.objects.create(username="two")
#         cls.user_three = User.objects.create(username="three")
#         cls.room = cls.meeting.rooms.create()
#         cls.system: SpeakerListSystem = cls.meeting.speaker_systems.create(
#             room=cls.room,
#             method_name=Priority.name,
#             state="active",
#             meeting_roles_to_speaker=[ROLE_PARTICIPANT],
#             safe_positions=0,
#         )
#         cls.slist: SpeakerList = cls.system.speaker_lists.create()
#         for user in [cls.user_one, cls.user_two, cls.user_three]:
#             cls.meeting.add_roles(user, ROLE_PARTICIPANT)
#
#     def _mk_enter(self, user):
#         return SpeakerListEnter(
#             mm={"user_pk": user.pk, "consumer_name": "abc"}, pk=self.slist.pk
#         )
#
#     def _mk_leave(self, user):
#         return SpeakerListLeave(
#             mm={"user_pk": user.pk, "consumer_name": "abc"}, pk=self.slist.pk
#         )
#
#     def _mk_leave_moderator(self, user):
#         return ModeratorSpeakerListLeave(
#             mm={"user_pk": self.moderator.pk, "consumer_name": "abc"},
#             pk=self.slist.pk,
#             user=user.pk,
#         )
#
#     def test_enter_with_history_order_check(self):
#         first = self.slist.speaker_items.create(
#             user=self.user_one, started=datetime(1911, 1, 1, tzinfo=UTC), seconds=1
#         )
#         second = self.slist.speaker_items.create(
#             user=self.user_two, started=datetime(1912, 1, 1, tzinfo=UTC), seconds=2
#         )
#         job_one = self._mk_enter(self.user_two)
#         job_one.run_job()
#         job_two = self._mk_enter(self.user_three)
#         job_two.run_job()
#         self.slist.refresh_from_db()
#         self.assertEqual([self.user_three.pk, self.user_two.pk], self.slist.order_list)
#
#     def test_leave_with_history(self):
#         first = self.slist.speaker_items.create(user=self.user_one)
#         second = self.slist.speaker_items.create(user=self.user_two)
#         first_historic = self.slist.speaker_items.create(
#             user=self.user_one, started=datetime(1911, 1, 1, tzinfo=UTC), seconds=1
#         )
#         third = self.slist.speaker_items.create(user=self.user_three)
#         self.slist.refresh_from_db()
#         self.assertEqual(
#             [self.user_two.pk, self.user_three.pk, self.user_one.pk],
#             self.slist.order_list,
#         )
#         second.delete()  # This will not trigger reorder, but it will still work next time
#         self.assertEqual(
#             [self.user_two.pk, self.user_three.pk, self.user_one.pk],
#             self.slist.order_list,
#         )
#         self.slist.reorder()
#         self.assertEqual(
#             [self.user_three.pk, self.user_one.pk],
#             self.slist.order_list,
#         )
#         job = self._mk_leave(self.user_three)
#         job.run_job()
#         self.slist.refresh_from_db()
#         self.assertEqual(
#             [self.user_one.pk],
#             self.slist.order_list,
#         )
#
#     def test_moderator_leave(self):
#         first = self.slist.speaker_items.create(user=self.user_one)
#         second = self.slist.speaker_items.create(user=self.user_two)
#         self.slist.refresh_from_db()
#         self.assertEqual(
#             [self.user_one.pk, self.user_two.pk],
#             self.slist.order_list,
#         )
#
#         job = self._mk_leave_moderator(self.user_one)
#         job.run_job()
#         self.slist.refresh_from_db()
#         self.assertEqual(
#             [self.user_two.pk],
#             self.slist.order_list,
#         )
#
#     @patch.object(ContextChannel, "sync_publish")  # All of them here
#     def test_full_delete_message_order(self, mock_publish):
#         self.system.active_list = self.slist
#         self.system.save()
#         first = self.slist.speaker_items.create(user=self.user_one)
#         second = self.slist.speaker_items.create(user=self.user_two)
#         first_historic = self.slist.speaker_items.create(
#             user=self.user_one, started=datetime(1911, 1, 1, tzinfo=UTC), seconds=1
#         )
#         mock_publish.reset_mock()
#         self.system.delete()
#         self.assertEqual(
#             [
#                 "speaker.deleted",
#                 "speaker.deleted",
#                 "speaker.deleted",
#                 "speaker_list.deleted",
#                 "speaker_system.deleted",
#             ],
#             [x.args[0].action for x in mock_publish.mock_calls],
#         )
