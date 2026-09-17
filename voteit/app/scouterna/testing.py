"""Testing helpers for the ScoutID backend."""

from __future__ import annotations

from django.conf import settings
from django.test import override_settings

from voteit.app.scouterna.backends import ScoutIDOpenIdConnect

BACKEND = f"{ScoutIDOpenIdConnect.__module__}.{ScoutIDOpenIdConnect.__qualname__}"


def scoutid_enabled() -> override_settings:
    """
    Add the ScoutID backend to AUTHENTICATION_BACKENDS for the duration.

    voteit ships as a package and a deployment is free to leave this backend
    out, so nothing here may depend on the running settings having it. Use as a
    class decorator or a context manager.

    voteit.organisation.signals.reload_social_backends refreshes social_core's
    backend cache when the setting changes, which is what makes this take
    effect at all.
    """
    others = [b for b in settings.AUTHENTICATION_BACKENDS if b != BACKEND]
    return override_settings(AUTHENTICATION_BACKENDS=[BACKEND, *others])
