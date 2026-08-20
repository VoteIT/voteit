from datetime import timedelta

from django.test import TestCase
from django.test import override_settings
from django.utils.timezone import now

from voteit.messaging.jobs import close_stale_connections
from voteit.messaging.models import ABNORMAL_CLOSURE
from voteit.messaging.models import NORMAL_CLOSURE
from voteit.messaging.models import Connection

STALE_JOB_AFTER = 60 * 60


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
