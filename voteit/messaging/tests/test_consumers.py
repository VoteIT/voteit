from unittest import mock

from django.dispatch import receiver
from django.test import TestCase
from pydantic import BaseModel
from rq import SimpleWorker
from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django_rq import get_queue
from fakeredis import FakeRedis

from voteit.core.queues import TESTING_QUEUE
from voteit.messaging.abcs import BaseIncomingMessage, AsyncRunnable, DeferredJob
from voteit.messaging.registries import incoming_messages

User = get_user_model()


class ConsumerIntegrationTests(TestCase):
    _connected = False

    def setUp(self):
        self.user = User.objects.create(username="sockety")
        self.fakeredis_conn = FakeRedis()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        # mock patch is probably the right way to do this
        incoming_messages.pop("testing", None)
        if self._connected:
            async_to_sync(self.communicator.disconnect)()

    def _mk_one(self):
        from voteit.messaging.consumers import WebsocketDemuxConsumer

        consumer = WebsocketDemuxConsumer()
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

    async def fixture(self):
        # FIXME: This is not the way tokens should work so this test will need to be changed later on.
        self.consumer = self._mk_one()
        self.communicator = WebsocketCommunicator(self.consumer, "/testws")
        connected, subprotocol = await self.communicator.connect()
        assert connected
        self._connected = True

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



    # FIXME:
    # test queue selecton!
    # async def test_receive_bad_data(self):
    #     pass
    #
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
