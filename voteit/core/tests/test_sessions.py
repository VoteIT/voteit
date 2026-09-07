"""Tracking session keys so "log out everywhere" can end them.

This is the layer that reaches a device with no socket open. The layer that
covers connected devices is the consumer flushing its own session, which is
tested in voteit.messaging.tests.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.test import override_settings

from voteit.core.sessions import MAX_TRACKED_SESSIONS
from voteit.core.sessions import cache_key
from voteit.core.sessions import end_tracked_sessions
from voteit.core.sessions import forget_session
from voteit.core.sessions import remember_session
from voteit.core.sessions import tracked_sessions
from voteit.core.testing import IsolatedCacheMixin
from voteit.organisation.models import Organisation

User = get_user_model()


class SessionTrackingTests(IsolatedCacheMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organisation = Organisation.objects.create(title="Org", host="testserver")
        cls.user = User.objects.create(username="user", organisation=cls.organisation)

    def test_nothing_tracked_by_default(self):
        self.assertEqual([], tracked_sessions(self.user.pk))

    def test_remember(self):
        remember_session(self.user.pk, "abc")
        self.assertEqual(["abc"], tracked_sessions(self.user.pk))

    def test_remembering_twice_does_not_duplicate(self):
        remember_session(self.user.pk, "abc")
        remember_session(self.user.pk, "abc")
        self.assertEqual(["abc"], tracked_sessions(self.user.pk))

    def test_keys_are_kept_per_user(self):
        other = User.objects.create(username="other", organisation=self.organisation)
        remember_session(self.user.pk, "abc")
        remember_session(other.pk, "def")
        self.assertEqual(["abc"], tracked_sessions(self.user.pk))
        self.assertEqual(["def"], tracked_sessions(other.pk))

    def test_oldest_keys_fall_off(self):
        """A ceiling on what one user can make us store."""
        for i in range(MAX_TRACKED_SESSIONS + 5):
            remember_session(self.user.pk, f"key-{i}")
        keys = tracked_sessions(self.user.pk)
        self.assertEqual(MAX_TRACKED_SESSIONS, len(keys))
        self.assertEqual(f"key-{MAX_TRACKED_SESSIONS + 4}", keys[-1])
        self.assertNotIn("key-0", keys)

    def test_forget_one(self):
        remember_session(self.user.pk, "abc")
        remember_session(self.user.pk, "def")
        forget_session(self.user.pk, "abc")
        self.assertEqual(["def"], tracked_sessions(self.user.pk))

    def test_forgetting_the_last_one_clears_the_entry(self):
        remember_session(self.user.pk, "abc")
        forget_session(self.user.pk, "abc")
        self.assertIsNone(cache.get(cache_key(self.user.pk)))

    def test_forgetting_an_unknown_key_is_harmless(self):
        remember_session(self.user.pk, "abc")
        forget_session(self.user.pk, "nope")
        self.assertEqual(["abc"], tracked_sessions(self.user.pk))

    def test_end_returns_how_many_and_clears(self):
        remember_session(self.user.pk, "abc")
        remember_session(self.user.pk, "def")
        self.assertEqual(2, end_tracked_sessions(self.user.pk))
        self.assertEqual([], tracked_sessions(self.user.pk))

    def test_ending_with_nothing_tracked_is_a_no_op(self):
        self.assertEqual(0, end_tracked_sessions(self.user.pk))

    def test_ending_tolerates_a_key_that_is_already_gone(self):
        """Entries outlive the sessions they name -- the cache TTL and the
        session TTL are not the same clock."""
        remember_session(self.user.pk, "expired-long-ago")
        self.assertEqual(1, end_tracked_sessions(self.user.pk))


class LoginRecordsTheKeyTests(IsolatedCacheMixin, TestCase):
    """The receiver, wired to user_logged_in in voteit.core.signals."""

    @classmethod
    def setUpTestData(cls):
        cls.organisation = Organisation.objects.create(title="Org", host="testserver")
        cls.user = User.objects.create(username="user", organisation=cls.organisation)

    def test_logging_in_records_the_session_key(self):
        self.client.force_login(self.user)
        self.assertEqual(
            [self.client.session.session_key], tracked_sessions(self.user.pk)
        )

    def test_a_second_login_records_both(self):
        self.client.force_login(self.user)
        first = self.client.session.session_key
        other = self.client_class()
        other.force_login(self.user)
        self.assertEqual(
            {first, other.session.session_key}, set(tracked_sessions(self.user.pk))
        )


@override_settings(SESSION_ENGINE="django.contrib.sessions.backends.db")
class EndTrackedSessionsDbBackendTests(IsolatedCacheMixin, TestCase):
    """End to end against a real session store.

    Production uses the cache backend, which cannot be inspected from here;
    the db backend exercises the same code path -- SESSION_ENGINE is resolved
    at call time -- and can be asserted on.
    """

    @classmethod
    def setUpTestData(cls):
        cls.organisation = Organisation.objects.create(title="Org", host="testserver")
        cls.user = User.objects.create(username="user", organisation=cls.organisation)

    def test_the_other_session_stops_working(self):
        other = self.client_class()
        other.force_login(self.user)
        self.assertIn(
            "_auth_user_id", other.session, "the fixture itself did not log in"
        )

        end_tracked_sessions(self.user.pk)

        from importlib import import_module

        store = import_module(settings.SESSION_ENGINE).SessionStore(
            session_key=other.cookies[settings.SESSION_COOKIE_NAME].value
        )
        self.assertNotIn("_auth_user_id", store.load())
