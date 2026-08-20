from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now

from voteit.messaging.admin import ConnectionStateFilter
from voteit.messaging.models import ABNORMAL_CLOSURE
from voteit.messaging.models import NORMAL_CLOSURE
from voteit.messaging.models import Connection
from voteit.organisation.models import Organisation

User = get_user_model()


class CountQueries(CaptureQueriesContext):
    def __init__(self):
        super().__init__(connection)

    @property
    def count(self):
        return len(self.captured_queries)


# 15 minutes, matching the shipped default.
STALE_AFTER = 15 * 60


@override_settings(VOTEIT_CONNECTION_STALE_AFTER=STALE_AFTER)
class ConnectionAdminTests(TestCase):
    changelist_url = reverse("admin:voteit_messaging_connection_changelist")
    online_url = reverse("admin:voteit_messaging_connection_online")

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create(title="First", host="first.example.com")
        cls.other_org = Organisation.objects.create(
            title="Second", host="second.example.com"
        )
        cls.user = User.objects.create(
            username="participant",
            userid="participant",
            email="participant@example.com",
            organisation=cls.org,
        )
        cls.other_user = User.objects.create(
            username="outsider", organisation=cls.other_org
        )
        cls.admin_user = User.objects.create_superuser(username="admin")

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_user)

    def _mk(self, user=None, *, name, ago=0, duration=60, code=None) -> Connection:
        """A connection last seen ``ago`` seconds back, ``duration`` seconds long."""
        last_action = now() - timedelta(seconds=ago)
        return Connection.objects.create(
            user_id=(user or self.user).pk,
            channel_name=name,
            connected_at=last_action - timedelta(seconds=duration),
            last_action=last_action,
            code=code,
        )

    def _mk_all(self):
        return {
            "online": self._mk(name="live", ago=5),
            "stale": self._mk(name="ghost", ago=3600),
            "closed": self._mk(name="bye", ago=7200, code=NORMAL_CLOSURE),
            "abnormal": self._mk(name="crash", ago=7200, code=ABNORMAL_CLOSURE),
        }

    def _pks(self, response):
        return {obj.pk for obj in response.context["cl"].result_list}

    def test_changelist_renders(self):
        conns = self._mk_all()
        response = self.client.get(self.changelist_url)
        self.assertEqual(200, response.status_code)
        self.assertEqual({c.pk for c in conns.values()}, self._pks(response))

    def test_changelist_shows_user_and_duration(self):
        self._mk(name="live", ago=5, duration=90)
        response = self.client.get(self.changelist_url)
        content = response.content.decode()
        self.assertIn(str(self.user), content)
        self.assertIn("1m", content)

    def test_rows_are_not_wrapped_in_a_change_link(self):
        """list_display_links=None keeps the user link from nesting anchors."""
        conn = self._mk(name="live", ago=5)
        content = self.client.get(self.changelist_url).content.decode()
        self.assertNotIn(f"/connection/{conn.pk}/change/", content)
        self.assertIn(f"/admin/core/user/{self.user.pk}/change/", content)

    def test_deleted_user_does_not_break_changelist(self):
        conn = self._mk(name="orphan", ago=5)
        Connection.objects.filter(pk=conn.pk).update(user_id=999999)
        response = self.client.get(self.changelist_url)
        self.assertEqual(200, response.status_code)
        self.assertIn("#999999 (deleted)", response.content.decode())

    def test_state_filter(self):
        conns = self._mk_all()
        for value, expected in (
            (ConnectionStateFilter.ONLINE, "online"),
            (ConnectionStateFilter.STALE, "stale"),
            (ConnectionStateFilter.CLOSED, "closed"),
            (ConnectionStateFilter.CLOSED_ABNORMALLY, "abnormal"),
        ):
            with self.subTest(state=value):
                response = self.client.get(self.changelist_url, {"state": value})
                self.assertEqual(200, response.status_code)
                self.assertEqual({conns[expected].pk}, self._pks(response))

    def test_organisation_filter(self):
        mine = self._mk(name="mine", ago=5)
        self._mk(self.other_user, name="theirs", ago=5)
        response = self.client.get(self.changelist_url, {"org": self.org.pk})
        self.assertEqual({mine.pk}, self._pks(response))

    def test_search(self):
        conn = self._mk(name="specific-channel", ago=5)
        self._mk(self.other_user, name="other-channel", ago=5)
        for term in (
            "participant@example.com",
            "participant",
            "specific-channel",
            str(self.user.pk),
        ):
            with self.subTest(term=term):
                response = self.client.get(self.changelist_url, {"q": term})
                self.assertEqual({conn.pk}, self._pks(response))

    def test_user_lookup_does_not_scale_with_rows(self):
        """ConnectionChangeList resolves the whole page in one in_bulk()."""
        for n in range(3):
            self._mk(name=f"c{n}", ago=5)
        with CountQueries() as few:
            self.client.get(self.changelist_url)
        # 37 more rows, each belonging to a different user.
        for n in range(3, 40):
            self._mk(User.objects.create(username=f"u{n}"), name=f"c{n}", ago=5)
        with CountQueries() as many:
            self.client.get(self.changelist_url)
        self.assertEqual(few.count, many.count)

    def test_close_stale_action(self):
        conns = self._mk_all()
        response = self.client.post(
            self.changelist_url,
            {
                "action": "close_stale_connections",
                "_selected_action": [str(c.pk) for c in conns.values()],
            },
            follow=True,
        )
        self.assertEqual(200, response.status_code)
        conns["stale"].refresh_from_db()
        conns["online"].refresh_from_db()
        self.assertEqual(ABNORMAL_CLOSURE, conns["stale"].code)
        self.assertIsNone(conns["online"].code)
        self.assertEqual(
            NORMAL_CLOSURE, Connection.objects.get(channel_name="bye").code
        )

    def test_close_stale_action_reports_skipped(self):
        conns = self._mk_all()
        response = self.client.post(
            self.changelist_url,
            {
                "action": "close_stale_connections",
                "_selected_action": [str(c.pk) for c in conns.values()],
            },
            follow=True,
        )
        text = " ".join(str(m) for m in response.context["messages"])
        self.assertIn("Closed 1 stale connection(s)", text)
        self.assertIn("3 selection(s) skipped", text)

    def test_read_only(self):
        conn = self._mk(name="live", ago=5)
        self.assertEqual(403, self.client.get(f"{self.changelist_url}add/").status_code)
        change_url = reverse("admin:voteit_messaging_connection_change", args=[conn.pk])
        # Change reverts to the read-only view for a superuser with only view
        # permission, so assert on the form instead of the status code.
        self.assertFalse(self.client.get(change_url).context["has_change_permission"])

    def test_online_view(self):
        self._mk(name="live-a", ago=5, duration=120)
        self._mk(name="live-b", ago=5, duration=30)
        self._mk(self.other_user, name="live-c", ago=5)
        self._mk(name="ghost", ago=3600)
        response = self.client.get(self.online_url)
        self.assertEqual(200, response.status_code)
        context = response.context
        self.assertEqual(3, context["socket_count"])
        self.assertEqual(2, context["user_count"])
        self.assertEqual(1.5, context["sockets_per_user"])
        self.assertEqual(1, context["stale_count"])
        self.assertEqual(15, context["minutes"])

    def test_online_view_per_organisation(self):
        self._mk(name="live-a", ago=5)
        self._mk(name="live-b", ago=5)
        self._mk(self.other_user, name="live-c", ago=5)
        rows = self.client.get(self.online_url).context["organisations"]
        # One user each, despite the first org holding two sockets.
        self.assertEqual(
            [(self.org, 1), (self.other_org, 1)],
            sorted(
                [(row["organisation"], row["users"]) for row in rows],
                key=lambda r: r[0].title,
            ),
        )

    def test_online_view_buckets(self):
        self._mk(name="fresh", ago=5, duration=60)
        self._mk(name="old", ago=5, duration=3 * 3600)
        buckets = {
            row["label"]: row["count"]
            for row in self.client.get(self.online_url).context["buckets"]
        }
        self.assertEqual(1, buckets["< 5 min"])
        self.assertEqual(1, buckets["2-8 h"])
        self.assertEqual(0, buckets["> 8 h"])

    def test_online_view_longest_first(self):
        self._mk(name="short", ago=5, duration=60)
        self._mk(name="long", ago=5, duration=7200)
        longest = self.client.get(self.online_url).context["longest"]
        self.assertEqual(["2h 0m", "1m"], [row["duration"] for row in longest])

    def test_online_view_window(self):
        self._mk(name="recent", ago=600)  # 10 minutes ago
        # Outside a 5 minute window, inside the 15 and 60 minute ones.
        self.assertEqual(0, self._window_count(5))
        self.assertEqual(1, self._window_count(15))
        self.assertEqual(1, self._window_count(60))

    def _window_count(self, minutes):
        response = self.client.get(self.online_url, {"window": minutes})
        self.assertEqual(minutes, response.context["minutes"])
        return response.context["socket_count"]

    def test_online_view_rejects_unknown_window(self):
        response = self.client.get(self.online_url, {"window": "999"})
        self.assertEqual(15, response.context["minutes"])
