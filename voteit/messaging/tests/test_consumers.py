from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING
from unittest import mock

from asgiref.sync import async_to_sync
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.dispatch import receiver
from django.test import TestCase
from django.test import override_settings
from django_rq import get_queue
from fakeredis import FakeRedis
from pydantic import BaseModel
from pydantic import ValidationError
from rq import SimpleWorker
from voteit.core.queues import TESTING_QUEUE
from voteit.messaging.abcs import AsyncRunnable
from voteit.messaging.abcs import BaseIncomingMessage
from voteit.messaging.abcs import DeferredJob
from voteit.messaging.registries import incoming_messages

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.messaging.consumers import WebsocketDemuxConsumer

User = get_user_model()


_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class ConsumerTests(TestCase):
    _connected = False

    def setUp(self):
        self.user: AbstractUser = User.objects.create(username="sockety")
        self.fakeredis_conn = FakeRedis()

        super().setUp()

    def tearDown(self):
        super().tearDown()
        # mock patch is probably the right way to do this
        incoming_messages.pop("tester", None)
        if self._connected:
            async_to_sync(self.communicator.disconnect)()

    @property
    def _cut(self):
        from voteit.messaging.consumers import WebsocketDemuxConsumer

        return WebsocketDemuxConsumer

    def _mk_one(self, **kwargs) -> WebsocketDemuxConsumer:
        consumer = self._cut(**kwargs)
        consumer.refresh_user = mock.AsyncMock(return_value=self.user)
        consumer.get_queue = mock.MagicMock(
            return_value=get_queue(name=TESTING_QUEUE, connection=self.fakeredis_conn)
        )
        return consumer

    def _mk_worker(self):
        queue = get_queue(
            TESTING_QUEUE, autocommit=True, connection=self.fakeredis_conn
        )
        # We may want to add all the optional worker classes from settings here
        return SimpleWorker(
            queues=[queue],
            connection=self.fakeredis_conn,
            disable_default_exception_handler=True,
            log_job_description=False,
        )

    async def _mk_communicator(self, consumer, **kwargs):
        self.communicator = WebsocketCommunicator(consumer, "/testws", **kwargs)
        connected, subprotocol = await self.communicator.connect()
        assert connected
        self._connected = True

    async def fixture(self):
        # FIXME: This is not the way tokens should work so this test will need to be changed later on.
        self.consumer = self._mk_one()
        await self._mk_communicator(self.consumer)

    def _mk_deferred_job(self):
        class Schema(BaseModel):
            username: str

        @incoming_messages
        class Incoming(BaseIncomingMessage, DeferredJob):
            name = "tester"
            schema = Schema
            data: Schema

            async def pre_queue(self, consumer):
                setattr(consumer, "hello", "world")

            def run_job(self):
                self.user.username = self.data.username
                self.user.save()

        return Incoming(
            {"type": "tester", "user_pk": self.user.pk}, {"username": "jane"}
        )

    async def test_user(self):
        await self.fixture()
        self.assertEqual(self.consumer.user, self.user)
        refetched_user = await sync_to_async(User.objects.get)(pk=self.user.pk)
        self.assertEqual(self.user, refetched_user)

    def test_connection_signal(self):
        from voteit.messaging.signals import client_connect

        @receiver(client_connect)
        def my_listener(user, **kw):
            user.username = "hello_world"
            user.save()

        async_to_sync(self.fixture)()
        self.assertEqual("sockety", self.user.username)
        worker = self._mk_worker()
        completed = worker.work(burst=True)
        self.assertTrue(completed)
        self.user.refresh_from_db()
        self.assertEqual("hello_world", self.user.username)

    async def test_close_signal(self):
        from voteit.messaging.signals import client_close

        @receiver(client_close)
        def my_listener(user, close_code, **kw):
            user.username = "closed_%s" % close_code
            user.save()

        await self.fixture()
        self.assertEqual("sockety", self.user.username)
        worker = self._mk_worker()
        await self.communicator.disconnect(code=1001)
        completed = await sync_to_async(worker.work)(burst=True)
        self.assertTrue(completed)
        await sync_to_async(self.user.refresh_from_db)()
        self.assertEqual("closed_1001", self.user.username)

    async def test_handle_message_no_action(self):
        class Schema(BaseModel):
            hello: str

        class Incoming(BaseIncomingMessage):
            name = "tester"
            schema = Schema
            data: Schema

        msg = Incoming({"type": "tester"}, {"hello": "world"})

        consumer = self._mk_one()
        with self.assertRaises(TypeError):
            await consumer.handle_message(msg)

    async def test_handle_message_async_runnable(self):
        class Schema(BaseModel):
            hello: str

        class Incoming(BaseIncomingMessage, AsyncRunnable):
            name = "tester"
            schema = Schema
            data: Schema

            async def run(self, consumer):
                setattr(consumer, "hello", "world")

        msg = Incoming({"type": "tester"}, {"hello": "world"})

        consumer = self._mk_one()
        await consumer.handle_message(msg)
        self.assertEqual("world", getattr(consumer, "hello"))

    async def test_handle_message_deferred_job_pre_queue(self):
        consumer = self._mk_one()
        msg = self._mk_deferred_job()
        await consumer.handle_message(msg)
        # Job isn't actually run
        self.assertEqual("world", getattr(consumer, "hello"))

    def test_handle_message_deferred_job_run_job(self):
        consumer = self._mk_one()
        msg = self._mk_deferred_job()
        async_to_sync(consumer.handle_message)(msg)
        worker = self._mk_worker()
        completed = worker.work(burst=True)
        self.assertTrue(completed)
        self.user.refresh_from_db()
        self.assertEqual("jane", self.user.username)

    async def test_receive_bad_data_type(self):
        consumer = self._mk_one()
        with self.assertRaises(ValueError):
            await consumer.receive(bytes_data=b"hsfsfsi")

    async def test_receive_bad_json(self):
        consumer = self._mk_one()
        self.assertIsNone(consumer.last_error)
        await consumer.receive("hsfsfsi")
        self.assertIsInstance(consumer.last_error, datetime)

    async def test_receive_payload_validation_error(self):
        await self.fixture()
        consumer = self.consumer
        original = consumer.send_error
        # Wrap in mock but still run the code
        consumer.send_error = mock.AsyncMock(side_effect=original)
        self.assertIsNone(consumer.last_error)
        msg = json.dumps({"t": "testing.count", "p": {"num": "a"}})
        await consumer.receive(msg)
        self.assertIsInstance(consumer.last_error, datetime)
        self.assertTrue(consumer.send_error.called)

    async def test_receive_last_recv(self):
        await self.fixture()
        consumer = self.consumer
        self.assertIsInstance(consumer.last_recv, datetime)
        last_recv = consumer.last_recv
        payload = json.dumps({"t": "testing.hello"})
        await consumer.receive(payload)
        self.assertNotEqual(last_recv, consumer.last_recv)

    async def test_websocket_send_bad_msg_type(self):
        consumer = self._mk_one()
        msg = {"Hello": "There!", "t": "i don't exist"}
        with self.assertRaises(ValidationError):
            await consumer.websocket_send(msg)

    async def test_websocket_send(self):
        await self.fixture()
        consumer = self.consumer
        last_sent = consumer.last_sent
        msg = {"t": "testing.hello", "p": {"greeting": "Hello!"}}
        await consumer.websocket_send(msg)
        self.assertGreater(consumer.last_sent, last_sent)

    async def test_receive_hello(self):
        await self.fixture()
        consumer = self.consumer
        msg = json.dumps({"t": "testing.hello"})
        await consumer.receive(msg)
        response = await self.communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(
            {
                "p": {"greeting": "Hello sockety!"},
                "t": "testing.hello",
                "i": None,
                "l": "en",
                "s": "s",
            },
            data,
        )

    async def test_outgoing_with_action(self):
        from voteit.messaging.messages.user import RefreshUser

        consumer = self._cut()
        consumer.channel_name = "abc"
        consumer.user = self.user
        consumer.refresh_user = mock.AsyncMock(return_value=None)
        msg = RefreshUser.create()
        envelope = {"p": msg.data.dict(), "t": msg.name}
        await consumer.internal_receive(envelope)
        self.assertTrue(consumer.refresh_user.called)

    # FIXME: I have no idea how to test this
    # async def test_lang_from_cookie(self):
    #     self.client.get("/ws/")
    # consumer = await self._mk_one()
    # communicator = await self._mk_communicator()
    # consumer = self.consumer

    async def test_lang_from_header(self):
        consumer = self._mk_one()
        await self._mk_communicator(consumer, headers=[("accept-language", "sv")])
        self.assertEqual("sv", consumer.user_lang)

    async def test_translation_async_runnable(self):
        consumer = self._mk_one()
        await self._mk_communicator(consumer, headers=[("accept-language", "sv")])
        self.assertEqual("sv", consumer.user_lang)
        msg = json.dumps({"t": "testing.hello"})
        await self.communicator.send_to(msg)
        response = await self.communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(
            {
                "p": {"greeting": "Hej sockety!"},
                "t": "testing.hello",
                "i": None,
                "l": "sv",
                "s": "s",
            },
            data,
        )

    async def test_translation_passed_to_deferred_task(self):
        from rq.queue import Queue

        Queue.enqueue = mock.MagicMock()
        consumer = self._mk_one()
        await self._mk_communicator(consumer, headers=[(b"accept-language", b"sv")])
        self.assertEqual("sv", consumer.user_lang)
        msg = json.dumps({"t": "testing.hello", "p": {"use_worker": "true"}})
        await consumer.receive(msg)
        self.assertEqual(
            "sv", Queue.enqueue.mock_calls[-1].kwargs["mm_data"].get("language")
        )

    async def test_translation_from_async_error(self):
        consumer = self._mk_one()
        await self._mk_communicator(consumer, headers=[("accept-language", "sv")])
        self.assertEqual("sv", consumer.user_lang)
        msg = json.dumps({"t": "i_dont_exist", "i": 1})
        await self.communicator.send_to(msg)
        response = await self.communicator.receive_from()
        data = json.loads(response)
        self.assertEqual("sv", data["l"])
        self.assertEqual(
            {
                "p": {
                    "errors": [
                        {
                            "loc": ["t"],
                            "msg": "Ingen inkommande meddelandetyp med namn i_dont_exist",
                            "type": "value_error",
                        }
                    ],
                    "msg": "Validation error",
                },
                "t": "error.validation",
                "i": "1",
                "l": "sv",
                "s": "f",
            },
            data,
        )

    # FIXME
    # async def test_websocket_send(self):
    #     pass
    #
    # async def test_post_error(self):
    #     pass
    #
    # async def test_internal_receive(self):
    #     pass
    #
    # async def test_send_error(self):
    #     pass

    # communicator = WebsocketCommunicator(self._cut.as_asgi(), "/ws/token")
    # connected, subprotocol = await communicator.connect()
    # assert connected
    # # Test sending text
    # await communicator.send_to(text_data="hello")
    # response = await communicator.receive_from()
    # assert response == "hello"
    # # Close
    # await communicator.disconnect()
