from unittest.mock import patch

from django.test import SimpleTestCase
from django.test import override_settings

from voteit.agenda.messages import AgendaChanged
from voteit.messaging.utils import Target
from voteit.messaging.utils import _send_now


class SendNowDispatchTests(SimpleTestCase):
    """Which of the two fan-out routes _send_now picks.

    What each route does is covered end-to-end in test_consumer; this is only
    about the switch, since a flag nothing reads is worse than no flag.
    """

    message = AgendaChanged(payload={"pk": 1})

    def _route(self, target: Target) -> str:
        with (
            patch("voteit.messaging.utils._send_passthrough") as passthrough,
            patch("voteit.messaging.utils._send_typed") as typed,
        ):
            _send_now(self.message, target)
        self.assertNotEqual(passthrough.called, typed.called, "Exactly one route")
        return "passthrough" if passthrough.called else "typed"

    @override_settings(VOTEIT_WS_FAST_FANOUT=True)
    def test_fast_fanout_uses_the_passthrough(self):
        self.assertEqual("passthrough", self._route(Target("meeting_1")))

    @override_settings(VOTEIT_WS_FAST_FANOUT=False)
    def test_flag_off_uses_chanx(self):
        self.assertEqual("typed", self._route(Target("meeting_1")))

    @override_settings(VOTEIT_WS_FAST_FANOUT=False)
    def test_non_default_layer_always_uses_the_passthrough(self):
        # chanx reads the layer off the consumer class, so it cannot honour a
        # per-target one.
        self.assertEqual("passthrough", self._route(Target("meeting_1", layer="other")))
