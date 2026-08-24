import asyncio
from datetime import timedelta
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from django.utils.timezone import now

from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.messaging.jobs import close_stale_connections
from voteit.messaging.jobs import recheck_job
from voteit.messaging.messages import ChannelLeft
from voteit.messaging.models import ABNORMAL_CLOSURE
from voteit.messaging.models import NORMAL_CLOSURE
from voteit.messaging.models import Connection
from voteit.messaging.testing import testing_channel_layers_setting
from voteit.organisation.models import Organisation

User = get_user_model()

STALE_JOB_AFTER = 60 * 60


@async_to_sync
async def receive_or_none(layer, channel_name, timeout=0.1):
    """What the channel layer has for this consumer, or None if nothing does.

    The in-memory layer's receive() waits forever, so a "nothing arrived"
    assertion needs its own deadline.
    """
    try:
        return await asyncio.wait_for(layer.receive(channel_name), timeout)
    except (asyncio.TimeoutError, TimeoutError):
        return None


@override_settings(VOTEIT_CONNECTION_STALE_JOB_AFTER=STALE_JOB_AFTER)
class CloseStaleConnectionsTests(TestCase):
    def _mk(self, *, name, ago, code=None) -> Connection:
        last_action = now() - timedelta(seconds=ago)
        return Connection.objects.create(
            user_id=1,
            channel_name=name,
            connected_at=last_action - timedelta(minutes=1),
            last_action=last_action,
            code=code,
        )

    def test_closes_silent_open_connections(self):
        ghost = self._mk(name="ghost", ago=2 * STALE_JOB_AFTER)
        self.assertEqual(1, close_stale_connections())
        ghost.refresh_from_db()
        self.assertEqual(ABNORMAL_CLOSURE, ghost.code)

    def test_spares_connections_inside_the_window(self):
        live = self._mk(name="live", ago=STALE_JOB_AFTER // 2)
        self.assertEqual(0, close_stale_connections())
        live.refresh_from_db()
        self.assertIsNone(live.code)

    def test_leaves_already_closed_rows_alone(self):
        closed = self._mk(name="bye", ago=2 * STALE_JOB_AFTER, code=NORMAL_CLOSURE)
        close_stale_connections()
        closed.refresh_from_db()
        self.assertEqual(NORMAL_CLOSURE, closed.code)

    def test_does_not_touch_last_action(self):
        """stats.populate_history_log derives online_duration from it."""
        ghost = self._mk(name="ghost", ago=2 * STALE_JOB_AFTER)
        before = ghost.last_action
        close_stale_connections()
        ghost.refresh_from_db()
        self.assertEqual(before, ghost.last_action)

    def test_purge_is_off_by_default(self):
        self._mk(name="ancient", ago=400 * 24 * 3600, code=NORMAL_CLOSURE)
        close_stale_connections()
        self.assertEqual(1, Connection.objects.count())

    @override_settings(VOTEIT_CONNECTION_RETENTION_DAYS=30)
    def test_purge_keeps_rows_inside_the_retention_window(self):
        self._mk(name="ancient", ago=60 * 24 * 3600, code=NORMAL_CLOSURE)
        self._mk(name="recent", ago=3600, code=NORMAL_CLOSURE)
        self._mk(name="live", ago=STALE_JOB_AFTER // 2)
        close_stale_connections()
        self.assertEqual(
            {"recent", "live"},
            set(Connection.objects.values_list("channel_name", flat=True)),
        )

    @override_settings(VOTEIT_CONNECTION_RETENTION_DAYS=30)
    def test_purge_reaches_rows_this_run_just_closed(self):
        """A long-dead open row is closed and then purged in the same pass."""
        self._mk(name="ancient-open", ago=60 * 24 * 3600)
        close_stale_connections()
        self.assertFalse(Connection.objects.exists())


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class RecheckJobTests(TestCase):
    """The job behind channel.recheck.

    Removing a role broadcasts RecheckSubscriptions to the user's own group;
    this job is what actually drops the channels that role was paying for.
    Nothing else revokes a subscription that has already been granted, so a
    channel this job fails to leave keeps receiving messages the user is no
    longer allowed to see.
    """

    consumer_channel = "specific.abcdef!ghijkl"

    @classmethod
    def setUpTestData(cls):
        cls.organisation = Organisation.objects.create(title="Org", host="testserver")
        cls.meeting = Meeting.objects.create(
            title="Meeting", organisation=cls.organisation
        )
        cls.moderator = User.objects.create(username="moderator")
        cls.participant = User.objects.create(username="participant")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.participant, ROLE_PARTICIPANT)

    def _recheck(self, user, *channel_types, pk=None):
        """Run the job and return the messages it sent."""
        sent = []
        subscriptions = [
            {"channel_type": name, "pk": self.meeting.pk if pk is None else pk}
            for name in channel_types
        ]
        with patch(
            "voteit.messaging.jobs._send", side_effect=lambda m, _c: sent.append(m)
        ):
            recheck_job(
                user_pk=user.pk if user is not None else 0,
                consumer_channel=self.consumer_channel,
                subscriptions=subscriptions,
            )
        return sent

    def test_keeps_a_subscription_the_user_still_qualifies_for(self):
        self.assertEqual([], self._recheck(self.moderator, "moderators"))

    def test_leaves_a_channel_the_user_no_longer_qualifies_for(self):
        sent = self._recheck(self.participant, "moderators")
        self.assertEqual([ChannelLeft], [type(m) for m in sent])
        self.assertEqual(self.meeting.pk, sent[0].payload.pk)
        self.assertEqual("moderators", sent[0].payload.channel_type)
        self.assertEqual(f"moderators_{self.meeting.pk}", sent[0].payload.channel_name)

    def test_checks_each_subscription_separately(self):
        """One revoked channel must not take the still-allowed ones with it."""
        sent = self._recheck(self.participant, "participants", "moderators")
        self.assertEqual(["moderators"], [m.payload.channel_type for m in sent])

    def test_leaves_when_the_context_is_gone(self):
        """A meeting deleted while a socket was subscribed to it."""
        sent = self._recheck(self.moderator, "participants", pk=self.meeting.pk + 1000)
        self.assertEqual(["participants"], [m.payload.channel_type for m in sent])

    def test_leaves_when_the_user_is_gone(self):
        sent = self._recheck(None, "participants")
        self.assertEqual(["participants"], [m.payload.channel_type for m in sent])

    def test_skips_an_unknown_channel_type(self):
        """Stale client state must not fail the job for the other entries."""
        sent = self._recheck(self.participant, "no-such-channel", "moderators")
        self.assertEqual(["moderators"], [m.payload.channel_type for m in sent])

    def test_discards_the_consumer_from_the_group(self):
        """The message is only half of it -- delivery has to stop too."""
        layer = get_channel_layer()
        group = f"moderators_{self.meeting.pk}"
        async_to_sync(layer.group_add)(group, self.consumer_channel)

        self._recheck(self.participant, "moderators")

        async_to_sync(layer.group_send)(group, {"type": "handle_group_message"})
        self.assertIsNone(receive_or_none(layer, self.consumer_channel))

    def test_keeps_an_allowed_consumer_in_the_group(self):
        layer = get_channel_layer()
        group = f"moderators_{self.meeting.pk}"
        async_to_sync(layer.group_add)(group, self.consumer_channel)

        self._recheck(self.moderator, "moderators")

        async_to_sync(layer.group_send)(group, {"type": "handle_group_message"})
        self.assertIsNotNone(receive_or_none(layer, self.consumer_channel))
