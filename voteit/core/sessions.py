"""Best-effort tracking of a user's session keys, so they can all be ended.

Django gives no way to enumerate one user's sessions, and the production
``SESSION_ENGINE`` is cache-backed (``project/settings.py``), so there is not
even a table to scan. The usual answer -- mixing a rotating value into
``get_session_auth_hash()`` -- needs a column on ``User``. This is the
migration-free stand-in: remember the key when a session is created, and delete
what we remembered when the user asks to be logged out everywhere.

It is deliberately called *best effort*, and the REST layer does not rely on it
alone:

- The cache list is read-modify-write, so two logins for the same user within
  milliseconds can lose one key.
- Sessions that already existed when this shipped were never recorded.
- Without ``REDIS_CACHE_LOCATION`` the default cache is a per-process
  ``LocMemCache``, so under several workers each one only knows its own logins.

Every device with a live socket is covered regardless, because
``VoteitConsumer.close_connection`` flushes its own session when asked --
see ``voteit.messaging.close.close_user_connections``. What this module adds is
the device that is logged in but not currently connected.
"""

from __future__ import annotations

from importlib import import_module

from django.conf import settings
from django.core.cache import cache

#: Enough for a plausible number of devices, and a ceiling on what one user can
#: make us store. Oldest keys fall off the front.
MAX_TRACKED_SESSIONS = 25


def cache_key(user_pk: int) -> str:
    return f"auth-sessions:{user_pk}"


def _session_store(session_key: str):
    """A store for an existing key, resolved the way Django's own middleware
    does -- so this works for the cache backend in production and the database
    backend in development and tests without knowing which is which."""
    return import_module(settings.SESSION_ENGINE).SessionStore(session_key=session_key)


def remember_session(user_pk: int, session_key: str) -> None:
    """Record that this user has a session with this key."""
    keys = [k for k in (cache.get(cache_key(user_pk)) or []) if k != session_key]
    keys.append(session_key)
    cache.set(
        cache_key(user_pk),
        keys[-MAX_TRACKED_SESSIONS:],
        timeout=settings.SESSION_COOKIE_AGE,
    )


def tracked_sessions(user_pk: int) -> list[str]:
    return list(cache.get(cache_key(user_pk)) or [])


def forget_session(user_pk: int, session_key: str) -> None:
    """Drop one key, so an ordinary logout does not leave a dead key behind."""
    keys = [k for k in tracked_sessions(user_pk) if k != session_key]
    if keys:
        cache.set(cache_key(user_pk), keys, timeout=settings.SESSION_COOKIE_AGE)
    else:
        cache.delete(cache_key(user_pk))


def end_tracked_sessions(user_pk: int) -> int:
    """Delete every session we know about for this user. Returns how many.

    Deleting a key that has already expired is a no-op in both backends, so
    stale entries cost nothing but the call.
    """
    keys = tracked_sessions(user_pk)
    for session_key in keys:
        _session_store(session_key).delete()
    cache.delete(cache_key(user_pk))
    return len(keys)
