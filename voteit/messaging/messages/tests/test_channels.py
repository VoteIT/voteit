from unittest import mock

from asgiref.sync import async_to_sync
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TestCase
from django_rq import get_queue
from fakeredis import FakeRedis
from rq import SimpleWorker
from voteit.core.queues import TESTING_QUEUE

User = get_user_model()


def _mk_consumer(user=None):
    from voteit.messaging.consumers import WebsocketDemuxConsumer

    consumer = WebsocketDemuxConsumer()
    consumer.channel_name = "abc"
    if user:
        consumer.user = user
        consumer.user_pk = user.pk
    return consumer


class SubscribeTests(TestCase):
    def setUp(self):
        self.user_jane = User.objects.create(username="jane")
        self.user_abel = User.objects.create(username="abel")

    @property
    def Subscribe(self):
        from voteit.messaging.messages.channels import Subscribe

        return Subscribe

    def test_subscribe(self):
        consumer = _mk_consumer(self.user_jane)
        msg = self.Subscribe(
            {"consumer_name": consumer.channel_name, "user_pk": self.user_jane.pk},
            pk=self.user_jane.pk,
            channel_type="user",
        )
        response = msg.run_job()
        async_to_sync(response.run)(consumer)
        self.assertIn(f"user_{self.user_jane.pk}", consumer.protected_subscriptions)

    def test_subscribe_unauthorized(self):
        from voteit.messaging.errors import UnauthorizedError

        consumer = _mk_consumer(self.user_jane)
        msg = self.Subscribe(
            {"consumer_name": consumer.channel_name, "user_pk": self.user_jane.pk},
            pk=self.user_abel.pk,
            channel_type="user",
        )
        self.assertRaises(UnauthorizedError, msg.run_job)


class LeaveTests(TestCase):
    def setUp(self):
        self.user_jane = User.objects.create(username="jane")
        self.user_abel = User.objects.create(username="abel")

    @property
    def Leave(self):
        from voteit.messaging.messages.channels import Leave

        return Leave

    def test_leave(self):
        consumer = _mk_consumer(self.user_jane)
        consumer.protected_subscriptions[f"user_{self.user_jane.pk}"] = "dummy"
        msg = self.Leave(
            {"consumer_name": consumer.channel_name, "user_pk": self.user_jane.pk},
            pk=self.user_jane.pk,
            channel_type="user",
        )
        response = msg.run_job()
        async_to_sync(response.run)(consumer)
        self.assertFalse(consumer.protected_subscriptions)

    def test_leave_unauthorized(self):
        from voteit.messaging.errors import UnauthorizedError

        consumer = _mk_consumer(self.user_jane)
        consumer.protected_subscriptions[f"user_{self.user_jane.pk}"] = "dummy"
        msg = self.Leave(
            {"consumer_name": consumer.channel_name, "user_pk": self.user_jane.pk},
            pk=self.user_abel.pk,
            channel_type="user",
        )
        self.assertRaises(UnauthorizedError, msg.run_job)


class RecheckChannelSubscriptionsTests(TestCase):
    def setUp(self):
        from voteit.messaging.consumers import WebsocketDemuxConsumer

        self.user_jane = User.objects.create(username="jane")
        self.user_abel = User.objects.create(username="abel")

        self.fakeredis_conn = FakeRedis()

        queue = get_queue(
            TESTING_QUEUE, autocommit=True, connection=self.fakeredis_conn
        )

        self.consumer = WebsocketDemuxConsumer()
        self.consumer.refresh_user = mock.AsyncMock(return_value=self.user_jane)
        self.consumer.get_queue = mock.MagicMock(return_value=queue)

        # We may want to add all the optional worker classes from settings here
        self.worker = SimpleWorker(
            queues=[queue],
            connection=self.fakeredis_conn,
            disable_default_exception_handler=True,
            log_job_description=False,
        )

        self._connected = False
        super().setUp()

    def tearDown(self):
        super().tearDown()
        if self._connected:
            async_to_sync(self.communicator.disconnect)()

    async def _connect(self):
        self.communicator = WebsocketCommunicator(self.consumer, "/testws")
        connected, subprotocol = await self.communicator.connect()
        assert connected
        self._connected = True

    @property
    def RecheckChannelSubscriptions(self):
        from voteit.messaging.messages.channels import RecheckChannelSubscriptions

        return RecheckChannelSubscriptions

    async def test_recheck(self):
        from voteit.messaging.messages.channels import ChannelSubscription

        await self._connect()
        jane_subs = ChannelSubscription(
            pk=self.user_jane.pk,
            channel_type="user",
            channel_name=f"user_{self.user_jane.pk}",
        )
        abel_subs = ChannelSubscription(
            pk=self.user_abel.pk,
            channel_type="user",
            channel_name=f"user_{self.user_abel.pk}",
        )
        self.consumer.protected_subscriptions[jane_subs.channel_name] = jane_subs
        # Not really allowed for user abel
        self.consumer.protected_subscriptions[abel_subs.channel_name] = abel_subs
        msg = self.RecheckChannelSubscriptions(
            {"consumer_name": self.consumer.channel_name, "user_pk": self.user_jane.pk},
            pk=self.user_jane.pk,
            channel_type="user",
        )
        await self.consumer.handle_message(msg)
        self.assertEqual(
            2, len(self.consumer.protected_subscriptions)
        )  # Worker hasn't worked yet
        completed = await sync_to_async(self.worker.work)(burst=True)
        self.assertTrue(completed)
        # One should've been removed
        self.assertEqual(1, len(self.consumer.protected_subscriptions))
