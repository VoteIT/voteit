from unittest.mock import MagicMock

from django.core.cache import cache
from django.test import TestCase

from voteit.core.rest_api.lock import LockAlreadyRunning
from voteit.core.rest_api.lock import LockCooldownActive
from voteit.core.rest_api.lock import RequestLock


def _make_request(session_key="test-session"):
    req = MagicMock()
    req.session.session_key = session_key
    return req


class RequestLockTests(TestCase):
    def setUp(self):
        self.lock = RequestLock("test_op")
        self.req = _make_request()

    def tearDown(self):
        cache.clear()

    # --- key helpers ---

    def test_processing_key_format(self):
        self.assertEqual(self.lock._processing_key("abc"), "test_op:processing:abc")

    def test_cooldown_key_format(self):
        self.assertEqual(self.lock._cooldown_key("abc"), "test_op:cooldown:abc")

    # --- acquire ---

    def test_acquire_sets_processing_key(self):
        self.lock.acquire(self.req)
        self.assertIsNotNone(cache.get(self.lock._processing_key("test-session")))

    def test_acquire_raises_already_running(self):
        cache.add(self.lock._processing_key("test-session"), 1, 60)
        with self.assertRaises(LockAlreadyRunning):
            self.lock.acquire(self.req)

    def test_acquire_raises_cooldown_active(self):
        cache.add(self.lock._cooldown_key("test-session"), 1, 60)
        with self.assertRaises(LockCooldownActive):
            self.lock.acquire(self.req)

    def test_cooldown_checked_before_processing_lock(self):
        cache.add(self.lock._processing_key("test-session"), 1, 60)
        cache.add(self.lock._cooldown_key("test-session"), 1, 60)
        with self.assertRaises(LockCooldownActive):
            self.lock.acquire(self.req)

    def test_acquire_creates_session_when_missing(self):
        req = MagicMock()
        req.session.session_key = None

        def _create():
            req.session.session_key = "new-session"

        req.session.create.side_effect = _create
        self.lock.acquire(req)
        req.session.create.assert_called_once()
        self.assertIsNotNone(cache.get(self.lock._processing_key("new-session")))

    # --- release ---

    def test_release_clears_processing_key(self):
        self.lock.acquire(self.req)
        self.lock.release(self.req)
        self.assertIsNone(cache.get(self.lock._processing_key("test-session")))

    def test_release_sets_cooldown_key(self):
        self.lock.acquire(self.req)
        self.lock.release(self.req)
        self.assertIsNotNone(cache.get(self.lock._cooldown_key("test-session")))

    def test_release_is_noop_without_session(self):
        req = _make_request(session_key=None)
        req.session.session_key = None
        self.lock.release(req)  # must not raise

    # --- custom messages ---

    def test_custom_already_running_message(self):
        lock = RequestLock("x", already_running_message="busy")
        cache.add(lock._processing_key("test-session"), 1, 60)
        with self.assertRaises(LockAlreadyRunning) as cm:
            lock.acquire(self.req)
        self.assertEqual(str(cm.exception), "busy")

    def test_custom_cooldown_message(self):
        lock = RequestLock("x", cooldown_message="slow down")
        cache.add(lock._cooldown_key("test-session"), 1, 60)
        with self.assertRaises(LockCooldownActive) as cm:
            lock.acquire(self.req)
        self.assertEqual(str(cm.exception), "slow down")

    # --- namespacing ---

    def test_different_keys_do_not_interfere(self):
        lock_a = RequestLock("ns_a")
        lock_b = RequestLock("ns_b")
        req = _make_request()
        lock_a.acquire(req)
        lock_b.acquire(req)  # must not raise
        lock_a.release(req)
        lock_b.release(req)
