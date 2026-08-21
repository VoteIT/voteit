"""The ASGI entry point.

The websocket was not origin-checked at all under envelope, so these guard the
validator staying in place rather than any behaviour we are changing.
"""

import importlib

from asgiref.sync import sync_to_async
from channels.security.websocket import OriginValidator
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.test import TestCase
from django.test import override_settings

import project.asgi
from voteit.messaging.testing import ws_test_settings

# What Channels' WebsocketDenier answers a rejected handshake with.
ORIGIN_DENIED_CODE = 1000


def build_application():
    """Re-import the ASGI module so it re-reads ALLOWED_HOSTS.

    ``AllowedHostsOriginValidator`` is a factory, not a lazy wrapper: it copies
    ``settings.ALLOWED_HOSTS`` once, when the module is imported. That is fine
    in production, where settings never change, but it means override_settings
    cannot reach the already-built application object.
    """
    return importlib.reload(project.asgi).application


@ws_test_settings
class OriginValidationTests(TestCase):
    def test_websocket_route_is_origin_checked(self):
        validator = project.asgi.application.application_mapping["websocket"]
        self.assertIsInstance(validator, OriginValidator)
        self.assertEqual(list(settings.ALLOWED_HOSTS), list(validator.allowed_origins))

    async def _connect_with_hosts(self, origin: str, allowed_hosts: list[str]):
        # Rebuild under the narrower ALLOWED_HOSTS, then put the module back.
        self.addCleanup(build_application)
        with override_settings(ALLOWED_HOSTS=allowed_hosts):
            application = await sync_to_async(build_application)()
            communicator = WebsocketCommunicator(
                application,
                "/ws/",
                headers=[(b"origin", origin.encode()), (b"host", b"testserver")],
            )
            try:
                return await communicator.connect()
            finally:
                await communicator.disconnect()

    async def test_foreign_origin_is_denied_before_the_consumer_runs(self):
        connected, code = await self._connect_with_hosts(
            "http://evil.example.com", ["testserver"]
        )
        self.assertFalse(connected)
        self.assertEqual(ORIGIN_DENIED_CODE, code)

    async def test_own_origin_reaches_the_consumer(self):
        connected, _ = await self._connect_with_hosts(
            "http://testserver", ["testserver"]
        )
        # Anonymous, so the consumer closes it right after -- but it did get as
        # far as the consumer, which is the point.
        self.assertTrue(connected)
