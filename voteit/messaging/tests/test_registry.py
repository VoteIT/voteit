"""The guards that keep the outgoing and channel registries unambiguous.

Both registries are keyed by a string the wire protocol depends on, and both
are populated by import side effects across a dozen apps. A silent overwrite
would send one app's messages through another app's schema, so registration
fails loudly instead. Nothing else exercises that.
"""

from __future__ import annotations

from typing import Literal

from chanx.messages.base import BaseMessage
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from pydantic import BaseModel

from voteit.messaging.channels import ContextChannel
from voteit.messaging.registry import action_of
from voteit.messaging.registry import all_outgoing_messages
from voteit.messaging.registry import batch_for
from voteit.messaging.registry import context_channel_registry
from voteit.messaging.registry import register_channel
from voteit.messaging.registry import register_outgoing


class Payload(BaseModel):
    pk: int


class RegisterOutgoingTests(SimpleTestCase):
    """These register into the process-wide registry, so each uses its own
    action name and cleans up after itself."""

    def _register(self, action: str, name: str = "Message"):
        message_cls = type(
            name,
            (BaseMessage,),
            {
                "__annotations__": {
                    "action": Literal[action],  # type: ignore[valid-type]
                    "payload": Payload,
                },
                "action": action,
                "__module__": __name__,
            },
        )
        registered = register_outgoing(message_cls)
        self.addCleanup(self._unregister, action)
        return registered

    def _unregister(self, action: str):
        from voteit.messaging.registry import _batch_for
        from voteit.messaging.registry import _outgoing

        message_cls = _outgoing.pop(action, None)
        _outgoing.pop(f"{action}.batch", None)
        _batch_for.pop(message_cls, None)

    def test_registering_generates_a_batch_sibling(self):
        message_cls = self._register("t.one")
        self.assertEqual("t.one.batch", action_of(batch_for(message_cls)))

    def test_both_the_message_and_its_batch_are_advertised(self):
        """passthrough_events is built from this, so a missing entry means the
        consumer silently drops the message."""
        message_cls = self._register("t.two")
        advertised = all_outgoing_messages()
        self.assertIn(message_cls, advertised)
        self.assertIn(batch_for(message_cls), advertised)

    def test_registering_the_same_class_twice_is_allowed(self):
        """Modules get imported more than once via autodiscovery."""
        message_cls = self._register("t.three")
        self.assertIs(message_cls, register_outgoing(message_cls))

    def test_two_classes_cannot_share_an_action(self):
        self._register("t.four", name="First")
        with self.assertRaises(ImproperlyConfigured) as caught:
            self._register("t.four", name="Second")
        self.assertIn("First", str(caught.exception))
        self.assertIn("Second", str(caught.exception))

    def test_batch_for_an_unregistered_message_says_what_to_do(self):
        class NotRegistered(BaseMessage):
            action: Literal["t.nope"] = "t.nope"
            payload: Payload

        with self.assertRaises(LookupError) as caught:
            batch_for(NotRegistered)
        self.assertIn("@outgoing", str(caught.exception))


class RegisterChannelTests(SimpleTestCase):
    def _channel_cls(self, name: str, cls_name: str = "Channel"):
        return type(
            cls_name,
            (ContextChannel,),
            {"name": name, "model": None, "permission": None},
        )

    def _register(self, name: str, cls_name: str = "Channel"):
        registered = register_channel(self._channel_cls(name, cls_name))
        self.addCleanup(context_channel_registry.pop, name, None)
        return registered

    def test_registering_makes_it_reachable_by_name(self):
        channel_cls = self._register("t-channel")
        self.assertIs(channel_cls, context_channel_registry["t-channel"])

    def test_registering_the_same_class_twice_is_allowed(self):
        channel_cls = self._register("t-channel-again")
        self.assertIs(channel_cls, register_channel(channel_cls))

    def test_two_classes_cannot_share_a_name(self):
        self._register("t-clash", cls_name="FirstChannel")
        with self.assertRaises(ImproperlyConfigured) as caught:
            self._register("t-clash", cls_name="SecondChannel")
        self.assertIn("FirstChannel", str(caught.exception))
        self.assertIn("SecondChannel", str(caught.exception))
