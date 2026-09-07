"""Counting who is online.

One implementation behind both the "Online now" admin page and the
online_connections command, so the two cannot report different numbers.

Every count means open *and* active recently: Channels never reports a consumer
that died with its process, so an open row alone is not evidence of presence.
That is the distinction most of these tests turn on.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils.timezone import now

from voteit.messaging.models import Connection
from voteit.messaging.presence import presence
from voteit.organisation.models import Organisation

User = get_user_model()
WINDOW = timedelta(minutes=15)


class PresenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.one = Organisation.objects.create(title="One", host="one.example.com")
        cls.two = Organisation.objects.create(title="Two", host="two.example.com")
        cls.alice = User.objects.create(username="alice", organisation=cls.one)
        cls.bob = User.objects.create(username="bob", organisation=cls.one)
        cls.carol = User.objects.create(username="carol", organisation=cls.two)

    @staticmethod
    def _connect(user, channel_name, **kwargs):
        return Connection.objects.create(
            user_id=user.pk, channel_name=channel_name, **kwargs
        )

    def test_nothing_online(self):
        counted = presence(WINDOW)
        self.assertEqual(0, counted.users)
        self.assertEqual(0, counted.sockets)
        self.assertEqual([], counted.organisations)
        self.assertEqual(0, counted.sockets_per_user)

    def test_totals_count_sockets_and_users_separately(self):
        """One person with three tabs is one user and three sockets."""
        self._connect(self.alice, "a1")
        self._connect(self.alice, "a2")
        self._connect(self.alice, "a3")
        counted = presence(WINDOW)
        self.assertEqual(1, counted.users)
        self.assertEqual(3, counted.sockets)
        self.assertEqual(3.0, counted.sockets_per_user)

    def test_per_organisation_breakdown(self):
        self._connect(self.alice, "a1")
        self._connect(self.alice, "a2")
        self._connect(self.bob, "b1")
        self._connect(self.carol, "c1")

        rows = presence(WINDOW).organisations

        self.assertEqual([self.one, self.two], [r.organisation for r in rows])
        self.assertEqual([2, 1], [r.users for r in rows])
        self.assertEqual([3, 1], [r.sockets for r in rows])

    def test_organisations_are_busiest_first(self):
        self._connect(self.carol, "c1")
        self._connect(self.alice, "a1")
        self._connect(self.bob, "b1")
        self.assertEqual(
            [self.one, self.two],
            [r.organisation for r in presence(WINDOW).organisations],
        )

    def test_a_closed_connection_is_not_online(self):
        self._connect(self.alice, "a1", code=1000)
        self.assertEqual(0, presence(WINDOW).sockets)

    def test_a_silent_connection_is_not_online(self):
        """Open but not heard from: almost always a socket that died with its
        process. Counting it would overstate presence indefinitely."""
        self._connect(self.alice, "a1", last_action=now() - timedelta(hours=2))
        self.assertEqual(0, presence(WINDOW).sockets)

    def test_the_window_decides(self):
        self._connect(self.alice, "a1", last_action=now() - timedelta(minutes=30))
        self.assertEqual(0, presence(timedelta(minutes=15)).sockets)
        self.assertEqual(1, presence(timedelta(minutes=60)).sockets)

    def test_a_user_without_an_organisation_is_counted_in_the_total_only(self):
        """The FK is nullable only to ease testing, so this should not happen
        in production -- but the rows must not silently fail to add up."""
        nomad = User.objects.create(username="nomad")
        self._connect(self.alice, "a1")
        self._connect(nomad, "n1")

        counted = presence(WINDOW)

        self.assertEqual(2, counted.users)
        self.assertEqual([1], [r.users for r in counted.organisations])
        self.assertEqual(1, counted.users_without_organisation)

    def test_no_orphans_in_the_ordinary_case(self):
        self._connect(self.alice, "a1")
        self.assertEqual(0, presence(WINDOW).users_without_organisation)

    def test_a_row_for_a_deleted_user_is_ignored(self):
        """Connection rows deliberately outlive the user they describe -- there
        is no FK -- so a stale user_id must not crash the count."""
        self._connect(self.alice, "a1")
        Connection.objects.create(user_id=99999, channel_name="ghost")
        counted = presence(WINDOW)
        self.assertEqual(2, counted.sockets)
        self.assertEqual([1], [r.sockets for r in counted.organisations])


class OnlineConnectionsCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.one = Organisation.objects.create(title="One", host="one.example.com")
        cls.alice = User.objects.create(username="alice", organisation=cls.one)

    def _call(self, *args):
        out = StringIO()
        call_command("online_connections", *args, stdout=out)
        return out.getvalue()

    def test_reports_the_organisation_and_the_total(self):
        Connection.objects.create(user_id=self.alice.pk, channel_name="a1")
        Connection.objects.create(user_id=self.alice.pk, channel_name="a2")
        output = self._call()
        self.assertIn("One", output)
        self.assertIn("TOTAL", output)
        # One user, two sockets.
        self.assertRegex(output, r"One\s+1\s+2")
        self.assertRegex(output, r"TOTAL\s+1\s+2")

    def test_runs_with_nobody_online(self):
        output = self._call()
        self.assertRegex(output, r"TOTAL\s+0\s+0")

    def test_the_window_is_configurable(self):
        Connection.objects.create(
            user_id=self.alice.pk,
            channel_name="a1",
            last_action=now() - timedelta(minutes=30),
        )
        self.assertRegex(self._call(), r"TOTAL\s+0\s+0")
        self.assertRegex(self._call("--window", "60"), r"TOTAL\s+1\s+1")
