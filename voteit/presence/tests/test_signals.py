import json
from unittest import mock

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.test import override_settings
from voteit.messaging.abcs import BaseOutgoingMessage

from voteit.messaging.channels.user import UserChannel
from voteit.messaging.consumers import WebsocketDemuxConsumer
from voteit.messaging.envelopes import OutgoingEnvelope
from voteit.presence.channels import PresenceCheckChannel
from voteit.presence.messages import PresenceAdded, PresenceCheckStatus, PresenceDeleted

User = get_user_model()


_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SignalsTests(TransactionTestCase):
    def setUp(self):
        from voteit.presence.models import PresenceSystem
        from voteit.presence.models import PresenceCheck
        from voteit.meeting.models import Meeting

        self.user = User.objects.create(username="creeper")
        self.moderator = User.objects.create(username="moderator")
        self.meeting = Meeting.objects.create()
        self.meeting.add_roles(self.user, "participant")
        self.meeting.add_roles(self.moderator, "moderator")
        self.system = PresenceSystem.objects.create(meeting=self.meeting)
        self.check = PresenceCheck.objects.create(presence_system=self.system)

    def _mk_presence(self):
        from voteit.presence.models import Presence
        return Presence.objects.create(user=self.user, presence_check=self.check)

    async def thread_setup(self):
        """ Don't run in setUp but in the test itself! """
        self.consumer = WebsocketDemuxConsumer(enable_connection_signals=False)
        self.consumer.refresh_user = mock.AsyncMock(return_value=self.user)
        self.communicator = WebsocketCommunicator(self.consumer, "/testws")
        connected, proto = await self.communicator.connect()
        assert connected

    async def get_outgoing_message(self):
        payload = await self.communicator.receive_from()
        data = json.loads(payload)
        envelope = OutgoingEnvelope(**data)
        return BaseOutgoingMessage.from_consumer(self.consumer, envelope)

    async def test_presence_add_user_channel(self):
        await self.thread_setup()
        user_ch = UserChannel.from_instance(self.user)
        await user_ch.async_subscribe(self.consumer.channel_name)
        presence = await sync_to_async(self._mk_presence)()
        msg = await self.get_outgoing_message()
        try:
            self.assertIsInstance(msg, PresenceAdded)
            self.assertEqual(msg.user, self.user)
            self.assertEqual(msg.data.pk, presence.pk)
        finally:
            await self.communicator.disconnect()

    async def test_presence_add_presence_channel(self):
        await self.thread_setup()
        check_ch = PresenceCheckChannel.from_instance(self.check)
        await check_ch.async_subscribe(self.consumer.channel_name)
        await sync_to_async(self._mk_presence)()
        msg = await self.get_outgoing_message()
        try:
            self.assertIsInstance(msg, PresenceCheckStatus)
            self.assertEqual(msg.data.present, 1)
            self.assertEqual(msg.data.pk, self.check.pk)
        finally:
            await self.communicator.disconnect()

    async def test_presence_deleted_user_channel(self):
        await self.thread_setup()
        presence = await sync_to_async(self._mk_presence)()
        presence_pk = presence.pk
        user_ch = UserChannel.from_instance(self.user)
        await user_ch.async_subscribe(self.consumer.channel_name)
        await sync_to_async(presence.delete)()
        msg = await self.get_outgoing_message()
        try:
            self.assertIsInstance(msg, PresenceDeleted)
            self.assertEqual(msg.user, self.user)
            self.assertEqual(msg.data.pk, presence_pk)
        finally:
            await self.communicator.disconnect()

    async def test_presence_deleted_presence_channel(self):
        await self.thread_setup()
        presence = await sync_to_async(self._mk_presence)()
        check_ch = PresenceCheckChannel.from_instance(self.check)
        await check_ch.async_subscribe(self.consumer.channel_name)
        await sync_to_async(presence.delete)()
        msg = await self.get_outgoing_message()
        try:
            self.assertIsInstance(msg, PresenceCheckStatus)
            self.assertEqual(msg.data.present, 0)
            self.assertEqual(msg.data.pk, self.check.pk)
        finally:
            await self.communicator.disconnect()
