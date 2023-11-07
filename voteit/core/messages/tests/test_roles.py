from json import loads
from unittest import mock
from unittest.mock import patch

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import TransactionTestCase
from django.test import override_settings
from django_rq import get_queue
from fakeredis import FakeRedis
from pydantic import ValidationError
from pythonjsonlogger.jsonlogger import JsonFormatter
from rq import SimpleWorker

from envelope.consumers.websocket import WebsocketConsumer
from envelope.messages.channels import ChannelSubscription
from envelope.messages.errors import UnauthorizedError
from envelope.messages.errors import ValidationErrorMsg
from voteit.core.schemas import RoleOutput
from voteit.core.testing import FakeCommit
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}
json_formatter = JsonFormatter()


def _record_to_dict(record):
    # Also to test jsonlogger
    output = json_formatter.format(record)
    return loads(output)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AvalableMeetingRolesTests(TestCase):
    def _mk_one(self, **kw):
        from voteit.core.messages.roles import AvailableRoles

        return AvailableRoles(mm={"consumer_name": "abc"}, **kw)

    async def test_get_meeting_roles(self):
        from voteit.core.messages.roles import AvailableRolesResponse

        consumer = WebsocketConsumer()
        consumer.channel_name = "abc"
        consumer.base_send = mock.AsyncMock()
        msg = self._mk_one(model="meeting")
        response = await msg.run(consumer=consumer)
        self.assertIsInstance(response, AvailableRolesResponse)
        self.assertIsInstance(response.data.roles[0], RoleOutput)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class MeetingRolesTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create(username="abel")
        self.user_b = User.objects.create(username="bret")
        self.user_c = User.objects.create(username="cain")
        self.meeting = Meeting.objects.create()

    def test_get_meeting_roles_unauthorized(self):
        self.meeting.add_roles(self.user_a, ROLE_PARTICIPANT, ROLE_MODERATOR)
        from voteit.core.messages.roles import GetRoles

        msg = GetRoles(pk=self.meeting.pk, model="meeting")
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_get_meeting_roles(self):
        from voteit.core.messages.roles import GetRoles
        from voteit.core.messages.roles import AssignedRolesResponse
        from envelope.utils import channel_layer

        self.meeting.add_roles(self.user_a, ROLE_PARTICIPANT, ROLE_MODERATOR)
        msg = GetRoles(
            mm={"user_pk": self.user_a.pk, "consumer_name": "abc"},
            pk=self.meeting.pk,
            model="meeting",
        )

        with patch.object(channel_layer, "send") as mock_method:
            response = msg.run_job()
            self.assertTrue(mock_method.called)
            self.assertIsInstance(response, AssignedRolesResponse)
            data = response.data
            self.assertEqual(1, len(data.items))
            self.assertIn(self.user_a.pk, [x[0] for x in data.items])
            self.assertEqual({ROLE_PARTICIPANT, ROLE_MODERATOR}, set(data.items[0][1]))


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AddRolesTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")

    def _mk_msg(self, actor, users, roles):
        from voteit.core.messages.roles import AddRoles

        return AddRoles(
            mm={"user_pk": actor.pk, "consumer_name": "abc"},
            users=users,
            roles=roles,
            pk=self.meeting.pk,
            model="meeting",
        )

    def test_change_gets_logged(self):
        msg = self._mk_msg(self.moderator, [self.participant.pk], [str(ROLE_DISCUSSER)])
        with self.assertLogs("voteit.event.roles") as logs:
            with FakeCommit():
                msg.run_job()
                self.assertEqual(0, len(logs.records))
            self.assertEqual(1, len(logs.records))
        data = _record_to_dict(logs.records[0])
        self.assertEqual(
            {
                "message": "Added",
                "context_name": "meeting",
                "context": 1,
                "org": 1,
                "meeting": 1,
                "actor": 1,
                "for_user": 2,
                "roles": [ROLE_DISCUSSER],
            },
            data,
        )

    def test_permission_checked(self):
        msg = self._mk_msg(
            self.participant, [self.participant.pk], [str(ROLE_DISCUSSER)]
        )
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_bad_user_pks(self):
        msg = self._mk_msg(self.moderator, [-1], [ROLE_DISCUSSER])
        self.assertRaises(ValidationErrorMsg, msg.run_job)

    def test_bad_role(self):
        msg = self._mk_msg(self.moderator, [self.participant.pk], ["jeff"])
        self.assertRaises(ValidationError, msg.run_job)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class RemoveRolesTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")

    def _mk_msg(self, actor, users, roles):
        from voteit.core.messages.roles import RemoveRoles

        return RemoveRoles(
            mm={"user_pk": actor.pk, "consumer_name": "abc"},
            users=users,
            roles=roles,
            pk=self.meeting.pk,
            model="meeting",
        )

    def test_change_gets_logged(self):
        msg = self._mk_msg(
            self.moderator, [self.participant.pk], [str(ROLE_PARTICIPANT)]
        )
        with self.assertLogs("voteit.event.roles") as logs:
            with FakeCommit():
                msg.run_job()
                self.assertEqual(0, len(logs.records))
            self.assertEqual(1, len(logs.records))
        data = _record_to_dict(logs.records[0])
        self.assertEqual(
            {
                "message": "Removed",
                "context_name": "meeting",
                "context": 1,
                "meeting": 1,
                "org": 1,
                "actor": 1,
                "for_user": 2,
                "roles": [str(ROLE_PARTICIPANT)],
            },
            data,
        )

    def test_permission_checked(self):
        msg = self._mk_msg(
            self.participant, [self.participant.pk], [str(ROLE_DISCUSSER)]
        )
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_bad_user_pks(self):
        msg = self._mk_msg(self.moderator, [-1], [str(ROLE_DISCUSSER)])
        self.assertRaises(ValidationErrorMsg, msg.run_job)

    def test_bad_role(self):
        msg = self._mk_msg(self.moderator, [self.participant.pk], ["jeff"])
        self.assertRaises(ValidationError, msg.run_job)


# FIXME: This was the old test
# @override_settings(CHANNEL_LAYERS=_channel_layers_setting)
# class RolesIntegrationTests(TransactionTestCase):
#     def setUp(self):
#         self.user_a = User.objects.create(username="abel")
#         self.user_b = User.objects.create(username="bret")
#         self.meeting = Meeting.objects.create()
#         self.meeting.add_roles(self.user_a, "moderator")
#         self.meeting.add_roles(self.user_b, "moderator")
#
#     async def test_roles_removed_kicks_user_from_protected_channel(self):
#         from voteit.meeting.channels import ModeratorsChannel
#         from voteit.messaging.messages.roles import RemoveRoles
#
#         fakeredis_conn = FakeRedis()
#
#         queue = get_queue(TESTING_QUEUE, autocommit=True, connection=fakeredis_conn)
#
#         worker = SimpleWorker(
#             queues=[queue],
#             connection=fakeredis_conn,
#             disable_default_exception_handler=True,
#             log_job_description=False,
#         )
#
#         consumer_a = WebsocketConsumer(enable_connection_signals=False)
#         consumer_a.get_user = mock.AsyncMock(return_value=self.user_a)
#         consumer_a.get_queue = mock.MagicMock(return_value=queue)
#
#         consumer_b = WebsocketConsumer(enable_connection_signals=False)
#         consumer_b.get_user = mock.AsyncMock(return_value=self.user_b)
#         consumer_b.get_queue = mock.MagicMock(return_value=queue)
#
#         # Subscribe both users to the moderator channel
#         mod_channel = ModeratorsChannel.from_instance(self.meeting)
#         subscription = ChannelSubscription(
#             pk=self.meeting.pk,
#             channel_type=mod_channel.name,
#             channel_name=mod_channel.channel_name,
#         )
#         consumer_a.mark_subscribed(subscription)
#         consumer_b.mark_subscribed(subscription)
#
#         # And connect
#         communicator_a = WebsocketCommunicator(consumer_a, "/testws")
#         connected_a, subprotocol = await communicator_a.connect()
#         assert connected_a
#
#         communicator_b = WebsocketCommunicator(consumer_b, "/testws")
#         connected_b, subprotocol = await communicator_b.connect()
#         assert connected_b
#         try:
#             # User A sends this message
#             msg = RemoveRoles(
#                 mm={"user_pk": self.user_a.pk},
#                 users=[self.user_a.pk, self.user_b.pk],
#                 roles=["moderator"],
#                 model="meeting",
#                 pk=self.meeting.pk,
#             )
#             await consumer_a.handle_message(msg)
#             completed = await sync_to_async(worker.work)(burst=True)
#             self.failUnless(completed)
#             # Consumers must receive the messages to act
#             await communicator_a.receive_from()
#             await communicator_b.receive_from()
#
#             self.assertFalse(consumer_a.subscriptions)
#             self.assertFalse(consumer_b.subscriptions)
#         finally:
#             await communicator_a.disconnect()
#             await communicator_b.disconnect()
