"""End-to-end tests for the websocket consumer.

There were none of these under envelope -- everything was tested at the
signal level -- so these are the only tests that exercise the wire format,
the subscribe stream and group fan-out for real.

WebsocketTestCase is a TransactionTestCase: no setUpTestData, tables are
truncated between tests, and objects must be re-fetched in setUp.
"""

import asyncio
import time
from unittest.mock import patch

from asgiref.sync import sync_to_async
from chanx.channels.testing import WebsocketTestCase
from django.db import transaction
from django.test import override_settings
from django.contrib.auth import get_user_model
from fakeredis import FakeRedis
from rq import Queue
from rq import SimpleWorker

from voteit.agenda.messages import AgendaChanged
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.messaging.channels import user_group
from voteit.messaging.consumer import VoteitConsumer
from voteit.messaging.messages import ChannelLeave
from voteit.messaging.messages import ChannelListSubscriptions
from voteit.messaging.messages import ChannelRef
from voteit.messaging.messages import ChannelSubscribe
from voteit.messaging.messages import CloseConnection
from voteit.messaging.messages import Ping
from voteit.messaging.messages import Pong
from voteit.messaging.messages import RecheckSubscriptions
from voteit.messaging.models import NORMAL_CLOSURE
from voteit.messaging.models import Connection
from voteit.messaging.testing import WS_TEST_ORIGIN_HEADER
from voteit.messaging.testing import widen_receive_timeout
from voteit.messaging.testing import ws_test_settings
from voteit.organisation.models import Organisation

User = get_user_model()


@ws_test_settings
class ConsumerTestCase(WebsocketTestCase):
    consumer = VoteitConsumer
    ws_path = "/ws/"

    def setUp(self):
        super().setUp()
        # An in-process redis, so these jobs cannot be stolen by an rqworker
        # running against the developer's own redis -- and so nothing leaks
        # between test runs.
        self.queue = Queue("default", connection=FakeRedis())
        queue_patch = patch("django_rq.get_queue", return_value=self.queue)
        queue_patch.start()
        self.addCleanup(queue_patch.stop)
        self.organisation = Organisation.objects.create(title="Org", host="testserver")
        self.meeting = Meeting.objects.create(
            title="Meeting", organisation=self.organisation
        )
        self.moderator = User.objects.create(username="moderator")
        self.participant = User.objects.create(username="participant")
        self.meeting.add_roles(self.moderator, ROLE_MODERATOR, ROLE_PARTICIPANT)
        self.meeting.add_roles(self.participant, ROLE_PARTICIPANT)

    def get_ws_headers(self):
        # The communicator runs the production ASGI stack, origin validation
        # included, so every handshake needs an Origin. See
        # voteit.messaging.testing.WS_TEST_ORIGIN_HEADER.
        return [WS_TEST_ORIGIN_HEADER]

    def create_communicator(self, **kwargs):
        communicator = super().create_communicator(**kwargs)
        widen_receive_timeout(communicator)
        return communicator

    async def _connect(self, user=None):
        """Connect, authenticated as user unless anonymous is wanted.

        An authenticated socket starts with s.versions, which is read here so
        every test starts from a quiet socket.
        """
        headers = list(self.ws_headers)
        if user is not None:
            await self.async_client.aforce_login(user)
            headers.append(
                (
                    b"cookie",
                    self.async_client.cookies.output(header="", sep="; ").encode(),
                )
            )
        communicator = self.create_communicator(headers=headers)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        if user is not None:
            self.versions = await self._receive_one(communicator)
        return communicator

    async def _receive_one(self, communicator, timeout=1):
        """Receive exactly one message.

        Not receive_all_messages(): nothing acks the connect, so a drain here
        could only end by running out its timeout -- a second per test, and
        the case that used to leave the socket cancelled.
        """
        raw = await communicator.receive_json_from(timeout)
        return communicator.consumer.outgoing_message_adapter.validate_python(raw)

    def _work(self):
        """Drain the subscribe queue with an in-process worker."""
        SimpleWorker([self.queue], connection=self.queue.connection).work(burst=True)
        failed = self.queue.failed_job_registry
        if failed.get_job_ids():
            from rq.job import Job

            job = Job.fetch(failed.get_job_ids()[0], connection=self.queue.connection)
            self.fail(f"subscribe job failed:\n{job.exc_info}")


class ConnectionTests(ConsumerTestCase):
    async def test_anonymous_is_closed(self):
        communicator = await self._connect()
        await communicator.assert_closed()

    async def test_authenticated_gets_versions(self):
        communicator = await self._connect(self.moderator)
        self.assertEqual("s.versions", self.versions.action)
        await communicator.disconnect()

    async def test_connection_row_created(self):
        communicator = await self._connect(self.moderator)
        exists = await Connection.objects.filter(
            user_id=self.moderator.pk, code__isnull=True
        ).aexists()
        self.assertTrue(exists)
        await communicator.disconnect()

    async def test_disconnect_records_close_code(self):
        communicator = await self._connect(self.moderator)
        await communicator.disconnect()
        conn = await Connection.objects.filter(user_id=self.moderator.pk).afirst()
        self.assertIsNotNone(conn.code)

    async def test_ping_pong(self):
        communicator = await self._connect(self.moderator)
        await communicator.send_message(Ping())
        messages = await communicator.receive_all_messages(timeout=1)
        self.assertIn(Pong(), messages)
        await communicator.disconnect()

    async def test_socket_survives_a_late_event_loop_wakeup(self):
        """A drain that times out must not take the socket down with it.

        Blocking the loop so that it wakes up past the drain's deadline used
        to make asgiref cancel the application task, and the next send then
        raised CancelledError instead of anything informative. See
        voteit.messaging.testing.widen_receive_timeout.
        """
        communicator = await self._connect(self.moderator)
        loop = asyncio.get_running_loop()
        loop.call_later(0.95, lambda: time.sleep(0.3))
        await communicator.receive_all_messages(timeout=1)
        self.assertFalse(communicator.future.cancelled())

        await communicator.send_message(Ping())
        messages = await communicator.receive_all_messages(timeout=1)
        self.assertIn(Pong(), messages)
        await communicator.disconnect()


class SubscribeTests(ConsumerTestCase):
    async def _subscribe(self, communicator, channel_type, pk):
        await communicator.send_message(
            ChannelSubscribe(payload={"channel_type": channel_type, "pk": pk})
        )
        # Handlers run in a background task, so wait for the completion ack
        # before running the worker -- otherwise the job is not enqueued yet.
        await communicator.receive_all_messages(timeout=1)
        # The handler only enqueues; the worker produces the stream.
        await sync_to_async(self._work)()
        return await communicator.receive_all_messages(
            stop_action="channel.state_complete", timeout=2
        )

    async def test_stream_order(self):
        communicator = await self._connect(self.moderator)
        messages = await self._subscribe(communicator, "meeting", self.meeting.pk)
        actions = [m.action for m in messages]
        self.assertEqual("channel.subscribed", actions[0])
        self.assertEqual("channel.state_complete", actions[-1])
        await communicator.disconnect()

    async def test_subscribed_payload(self):
        communicator = await self._connect(self.moderator)
        messages = await self._subscribe(communicator, "meeting", self.meeting.pk)
        subscribed = next(m for m in messages if m.action == "channel.subscribed")
        self.assertEqual(self.meeting.pk, subscribed.payload.pk)
        self.assertEqual("meeting", subscribed.payload.channel_type)
        self.assertEqual(f"meeting_{self.meeting.pk}", subscribed.payload.channel_name)
        await communicator.disconnect()

    async def test_permission_denied(self):
        communicator = await self._connect(self.participant)
        await communicator.send_message(
            ChannelSubscribe(
                payload={"channel_type": "moderators", "pk": self.meeting.pk}
            )
        )
        await communicator.receive_all_messages(timeout=1)
        await sync_to_async(self._work)()
        messages = await communicator.receive_all_messages(
            stop_action="channel.subscribe_error", timeout=2
        )
        actions = [m.action for m in messages]
        self.assertIn("channel.subscribe_error", actions)
        self.assertNotIn("channel.subscribed", actions)
        await communicator.disconnect()

    async def test_unknown_channel_type_never_reaches_the_queue(self):
        communicator = await self._connect(self.moderator)
        await communicator.send_message(
            ChannelSubscribe(payload={"channel_type": "nope", "pk": 1})
        )
        messages = await communicator.receive_all_messages(
            stop_action="channel.subscribe_error", timeout=2
        )
        self.assertIn("channel.subscribe_error", [m.action for m in messages])
        await communicator.disconnect()

    async def test_group_fanout(self):
        communicator = await self._connect(self.moderator)
        await self._subscribe(communicator, "meeting", self.meeting.pk)
        await sync_to_async(MeetingChannel(self.meeting.pk).sync_publish)(
            AgendaChanged(payload={"pk": 1, "title": "Hello"}), on_commit=False
        )
        messages = await communicator.receive_all_messages(
            stop_action="agenda_item.changed", timeout=2
        )
        changed = [m for m in messages if m.action == "agenda_item.changed"]
        self.assertEqual(1, len(changed))
        self.assertEqual("Hello", changed[0].payload.title)
        await communicator.disconnect()

    async def test_group_fanout_typed_path(self):
        # VOTEIT_WS_FAST_FANOUT=False routes the same message through chanx's
        # event dispatcher instead, which re-validates it per recipient. The
        # frame the client sees must be identical.
        communicator = await self._connect(self.moderator)
        await self._subscribe(communicator, "meeting", self.meeting.pk)
        with override_settings(VOTEIT_WS_FAST_FANOUT=False):
            await sync_to_async(MeetingChannel(self.meeting.pk).sync_publish)(
                AgendaChanged(payload={"pk": 1, "title": "Hello"}), on_commit=False
            )
            messages = await communicator.receive_all_messages(
                stop_action="agenda_item.changed", timeout=2
            )
        changed = [m for m in messages if m.action == "agenda_item.changed"]
        self.assertEqual(1, len(changed))
        self.assertEqual("Hello", changed[0].payload.title)
        await communicator.disconnect()

    async def test_batch_collapse_end_to_end(self):
        """Several changes in one transaction arrive as one batch."""
        communicator = await self._connect(self.moderator)
        await self._subscribe(communicator, "meeting", self.meeting.pk)

        def publish_four():
            with transaction.atomic():
                channel = MeetingChannel(self.meeting.pk)
                for pk in range(4):
                    channel.sync_publish(AgendaChanged(payload={"pk": pk}))

        await sync_to_async(publish_four)()
        messages = await communicator.receive_all_messages(
            stop_action="agenda_item.changed.batch", timeout=2
        )
        batches = [m for m in messages if m.action == "agenda_item.changed.batch"]
        self.assertEqual(1, len(batches))
        self.assertEqual([0, 1, 2, 3], [x.pk for x in batches[0].payload.items])
        self.assertEqual([], [m for m in messages if m.action == "agenda_item.changed"])
        await communicator.disconnect()

    async def test_below_threshold_stays_individual(self):
        communicator = await self._connect(self.moderator)
        await self._subscribe(communicator, "meeting", self.meeting.pk)

        def publish_two():
            with transaction.atomic():
                channel = MeetingChannel(self.meeting.pk)
                for pk in range(2):
                    channel.sync_publish(AgendaChanged(payload={"pk": pk}))

        await sync_to_async(publish_two)()
        messages = await communicator.receive_all_messages(timeout=2)
        self.assertEqual(
            2, len([m for m in messages if m.action == "agenda_item.changed"])
        )
        self.assertEqual([], [m for m in messages if m.action.endswith(".batch")])
        await communicator.disconnect()

    async def test_leave_stops_delivery(self):
        communicator = await self._connect(self.moderator)
        await self._subscribe(communicator, "meeting", self.meeting.pk)
        await communicator.send_message(
            ChannelLeave(payload={"channel_type": "meeting", "pk": self.meeting.pk})
        )
        messages = await communicator.receive_all_messages(
            stop_action="channel.left", timeout=2
        )
        self.assertIn("channel.left", [m.action for m in messages])
        # Drain the completion ack so receive_nothing() below is meaningful.
        await communicator.receive_all_messages(timeout=1)
        await sync_to_async(MeetingChannel(self.meeting.pk).sync_publish)(
            AgendaChanged(payload={"pk": 1}), on_commit=False
        )
        self.assertTrue(await communicator.receive_nothing(timeout=0.5))
        await communicator.disconnect()

    async def test_list_subscriptions(self):
        communicator = await self._connect(self.moderator)
        await self._subscribe(communicator, "meeting", self.meeting.pk)
        await self._subscribe(communicator, "moderators", self.meeting.pk)
        await communicator.send_message(ChannelListSubscriptions())
        messages = await communicator.receive_all_messages(
            stop_action="channel.subscriptions", timeout=2
        )
        listed = next(m for m in messages if m.action == "channel.subscriptions")
        self.assertEqual(
            {
                ChannelRef(pk=self.meeting.pk, channel_type="meeting"),
                ChannelRef(pk=self.meeting.pk, channel_type="moderators"),
            },
            set(listed.payload.subscriptions),
        )
        await communicator.disconnect()

    async def test_missing_context_yields_subscribe_error(self):
        """A meeting deleted between listing it and subscribing to it.

        The worker must answer, not fail the job -- _work() fails the test if
        the job ends up in the failed registry.
        """
        communicator = await self._connect(self.moderator)
        await communicator.send_message(
            ChannelSubscribe(
                payload={"channel_type": "meeting", "pk": self.meeting.pk + 1000}
            )
        )
        await communicator.receive_all_messages(timeout=1)
        await sync_to_async(self._work)()
        messages = await communicator.receive_all_messages(
            stop_action="channel.subscribe_error", timeout=2
        )
        actions = [m.action for m in messages]
        self.assertIn("channel.subscribe_error", actions)
        self.assertNotIn("channel.subscribed", actions)
        await communicator.disconnect()


class RecheckTests(ConsumerTestCase):
    """Losing a role has to take the subscriptions it paid for with it.

    A subscription is only permission-checked once, when it is granted, so
    channel.recheck is the entire mechanism for revoking one on a socket that
    is already open. Removing a role in the REST layer broadcasts it.
    """

    async def _subscribe(self, communicator, channel_type, pk):
        await communicator.send_message(
            ChannelSubscribe(payload={"channel_type": channel_type, "pk": pk})
        )
        await communicator.receive_all_messages(timeout=1)
        await sync_to_async(self._work)()
        return await communicator.receive_all_messages(
            stop_action="channel.state_complete", timeout=2
        )

    async def _recheck(self, communicator, user):
        await sync_to_async(VoteitConsumer.broadcast_event_sync)(
            RecheckSubscriptions(), user_group(user.pk)
        )
        # The handler only enqueues; let it get that far before working.
        await communicator.receive_all_messages(timeout=1)
        await sync_to_async(self._work)()

    async def test_revoked_channel_is_left(self):
        communicator = await self._connect(self.moderator)
        await self._subscribe(communicator, "moderators", self.meeting.pk)

        await sync_to_async(self.meeting.remove_roles)(self.moderator, ROLE_MODERATOR)
        await self._recheck(communicator, self.moderator)

        messages = await communicator.receive_all_messages(
            stop_action="channel.left", timeout=2
        )
        left = [m for m in messages if m.action == "channel.left"]
        self.assertEqual(1, len(left))
        self.assertEqual("moderators", left[0].payload.channel_type)
        self.assertEqual(self.meeting.pk, left[0].payload.pk)
        await communicator.disconnect()

    async def test_revoked_channel_stops_delivering(self):
        """The channel.left message is only half of it."""
        communicator = await self._connect(self.moderator)
        await self._subscribe(communicator, "moderators", self.meeting.pk)

        await sync_to_async(self.meeting.remove_roles)(self.moderator, ROLE_MODERATOR)
        await self._recheck(communicator, self.moderator)
        await communicator.receive_all_messages(stop_action="channel.left", timeout=2)
        await communicator.receive_all_messages(timeout=1)

        await sync_to_async(ModeratorsChannel(self.meeting.pk).sync_publish)(
            AgendaChanged(payload={"pk": 1, "title": "Secret"}), on_commit=False
        )
        self.assertTrue(await communicator.receive_nothing(timeout=0.5))
        await communicator.disconnect()

    async def test_still_allowed_channel_is_kept(self):
        """Losing moderator must not cost the plain meeting channel."""
        communicator = await self._connect(self.moderator)
        await self._subscribe(communicator, "meeting", self.meeting.pk)
        await self._subscribe(communicator, "moderators", self.meeting.pk)

        await sync_to_async(self.meeting.remove_roles)(self.moderator, ROLE_MODERATOR)
        await self._recheck(communicator, self.moderator)
        await communicator.receive_all_messages(stop_action="channel.left", timeout=2)
        await communicator.receive_all_messages(timeout=1)

        await sync_to_async(MeetingChannel(self.meeting.pk).sync_publish)(
            AgendaChanged(payload={"pk": 1, "title": "Public"}), on_commit=False
        )
        messages = await communicator.receive_all_messages(
            stop_action="agenda_item.changed", timeout=2
        )
        self.assertIn("agenda_item.changed", [m.action for m in messages])
        await communicator.disconnect()

    async def test_left_channel_drops_out_of_list_subscriptions(self):
        """on_left has to keep the consumer's own set in step."""
        communicator = await self._connect(self.moderator)
        await self._subscribe(communicator, "meeting", self.meeting.pk)
        await self._subscribe(communicator, "moderators", self.meeting.pk)

        await sync_to_async(self.meeting.remove_roles)(self.moderator, ROLE_MODERATOR)
        await self._recheck(communicator, self.moderator)
        await communicator.receive_all_messages(stop_action="channel.left", timeout=2)

        await communicator.send_message(ChannelListSubscriptions())
        messages = await communicator.receive_all_messages(
            stop_action="channel.subscriptions", timeout=2
        )
        listed = next(m for m in messages if m.action == "channel.subscriptions")
        self.assertEqual(
            [ChannelRef(pk=self.meeting.pk, channel_type="meeting")],
            listed.payload.subscriptions,
        )
        await communicator.disconnect()

    async def test_nothing_subscribed_never_reaches_the_queue(self):
        communicator = await self._connect(self.moderator)
        await self._recheck(communicator, self.moderator)
        self.assertEqual([], self.queue.job_ids)
        self.assertTrue(await communicator.receive_nothing(timeout=0.5))
        await communicator.disconnect()

    async def test_recheck_keeps_everything_when_nothing_changed(self):
        communicator = await self._connect(self.moderator)
        await self._subscribe(communicator, "moderators", self.meeting.pk)

        await self._recheck(communicator, self.moderator)

        self.assertTrue(await communicator.receive_nothing(timeout=0.5))
        await communicator.disconnect()


class CloseConnectionTests(ConsumerTestCase):
    """s.close, the server-side "go away" -- e.g. on logout.

    Nothing in the repo sends it yet, so these tests are the only thing
    holding the handler to its contract.
    """

    async def test_warns_before_closing(self):
        communicator = await self._connect(self.moderator)
        await sync_to_async(VoteitConsumer.broadcast_event_sync)(
            CloseConnection(payload={"code": 4001}), user_group(self.moderator.pk)
        )
        messages = await communicator.receive_all_messages(
            stop_action="s.closing", timeout=2
        )
        closing = next(m for m in messages if m.action == "s.closing")
        self.assertEqual(4001, closing.payload.code)

    async def test_socket_is_closed_with_the_requested_code(self):
        """assert_closed() is not used here -- it only matches a bare close
        frame, and the whole point of s.close is the code it carries."""
        communicator = await self._connect(self.moderator)
        await sync_to_async(VoteitConsumer.broadcast_event_sync)(
            CloseConnection(payload={"code": 4001}), user_group(self.moderator.pk)
        )
        await communicator.receive_all_messages(stop_action="s.closing", timeout=2)
        self.assertEqual(
            {"type": "websocket.close", "code": 4001},
            await communicator.receive_output(),
        )

    async def test_default_code_is_a_normal_closure(self):
        communicator = await self._connect(self.moderator)
        await sync_to_async(VoteitConsumer.broadcast_event_sync)(
            CloseConnection(), user_group(self.moderator.pk)
        )
        await communicator.receive_all_messages(stop_action="s.closing", timeout=2)
        self.assertEqual(
            {"type": "websocket.close", "code": NORMAL_CLOSURE},
            await communicator.receive_output(),
        )
