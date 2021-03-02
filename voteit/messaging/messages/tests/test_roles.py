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
from rq import SimpleWorker
from voteit.core.queues import TESTING_QUEUE
from voteit.core.schemas import RoleOutput
from voteit.meeting.models import Meeting
from voteit.messaging.errors import UnauthorizedError

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AvalableMeetingRolesTests(TestCase):
    def _mk_one(self, **kw):
        from voteit.messaging.messages.roles import AvailableRoles

        return AvailableRoles(mm={"consumer_name": "abc"}, **kw)

    async def test_get_meeting_roles(self):
        from voteit.messaging.messages.roles import AvailableRolesResponse

        msg = self._mk_one(natural_key="meeting.meeting")
        response = await msg.run(None)
        self.assertIsInstance(response, AvailableRolesResponse)
        self.assertIsInstance(response.data.roles[0], RoleOutput)

    async def test_get_bad_types_and_names(self):
        self.assertRaises(ValidationError, self._mk_one, natural_key="meetingmeeting")
        self.assertRaises(ValidationError, self._mk_one, natural_key="poll.poll")


class MeetingRolesTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create(username="abel")
        self.user_b = User.objects.create(username="bret")
        self.user_c = User.objects.create(username="cain")
        self.meeting = Meeting.objects.create()

    def test_get_meeting_roles_unauthorized(self):
        self.meeting.add_roles(self.user_a, "participant", "moderator")
        from voteit.messaging.messages.roles import GetMeetingRoles

        msg = GetMeetingRoles({}, pk=self.meeting.pk)
        self.assertRaises(UnauthorizedError, msg.run_job)

    def test_get_meeting_roles(self):
        self.meeting.add_roles(self.user_a, "participant", "moderator")
        from voteit.messaging.messages.roles import GetMeetingRoles
        from voteit.messaging.messages.roles import AssignedMeetingRolesResponse

        msg = GetMeetingRoles({"user_pk": self.user_a.pk}, pk=self.meeting.pk)

        with patch.object(AssignedMeetingRolesResponse, "send_outgoing") as mock_method:
            response = msg.run_job()
            self.assertTrue(mock_method.called)
            self.assertIsInstance(response, AssignedMeetingRolesResponse)

            res_dict = response.data.dict()
            self.assertEqual(1, len(res_dict["items"]))
            res_items = res_dict["items"]
            self.assertIn(self.user_a.pk, res_items)
            self.assertEqual(
                {"participant", "moderator"}, set(res_items[self.user_a.pk])
            )


class RolesIntegrationTests(TransactionTestCase):
    def setUp(self):
        self.user_a = User.objects.create(username="abel")
        self.user_b = User.objects.create(username="bret")
        self.meeting = Meeting.objects.create()
        self.meeting.add_roles(self.user_a, "moderator")
        self.meeting.add_roles(self.user_b, "moderator")

    async def test_roles_removed_kicks_user_from_protected_channel(self):
        from voteit.messaging.consumers import WebsocketDemuxConsumer
        from voteit.meeting.channels import ModeratorsChannel
        from voteit.messaging.messages.channels import ChannelSubscription
        from voteit.messaging.messages.roles import RemoveMeetingRoles

        fakeredis_conn = FakeRedis()

        queue = get_queue(TESTING_QUEUE, autocommit=True, connection=fakeredis_conn)

        worker = SimpleWorker(
            queues=[queue],
            connection=fakeredis_conn,
            disable_default_exception_handler=True,
            log_job_description=False,
        )

        consumer_a = WebsocketDemuxConsumer()
        consumer_a.refresh_user = mock.AsyncMock(return_value=self.user_a)
        consumer_a.get_queue = mock.MagicMock(return_value=queue)

        consumer_b = WebsocketDemuxConsumer()
        consumer_b.refresh_user = mock.AsyncMock(return_value=self.user_b)
        consumer_b.get_queue = mock.MagicMock(return_value=queue)

        # Subscribe both users to the moderator channel
        mod_channel = ModeratorsChannel.from_instance(self.meeting)
        subscription = ChannelSubscription(
            pk=self.meeting.pk,
            channel_type=mod_channel.name,
            channel_name=mod_channel.channel_name,
        )
        consumer_a.mark_subscribed(subscription)
        consumer_b.mark_subscribed(subscription)

        # And connect
        communicator_a = WebsocketCommunicator(consumer_a, "/testws")
        connected_a, subprotocol = await communicator_a.connect()
        assert connected_a

        communicator_b = WebsocketCommunicator(consumer_b, "/testws")
        connected_b, subprotocol = await communicator_b.connect()
        assert connected_b

        try:
            # User A sends this message
            msg = RemoveMeetingRoles(
                mm={"user_pk": self.user_a.pk},
                userids=[self.user_a.pk, self.user_b.pk],
                roles=["moderator"],
                pk=self.meeting.pk,
            )
            await consumer_a.handle_message(msg)
            completed = await sync_to_async(worker.work)(burst=True)
            self.failUnless(completed)
            # Consumers must receive the messages to act
            await communicator_a.receive_from()
            await communicator_b.receive_from()

            self.assertFalse(consumer_a.protected_subscriptions)
            self.assertFalse(consumer_b.protected_subscriptions)
        finally:
            await communicator_a.disconnect()
            await communicator_b.disconnect()
