from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from voteit.core.messages.user import InvalidateUserCache
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.models import Meeting
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.jobs import _applicable
from voteit.messaging.jobs import _collect
from voteit.messaging.registry import CollectorRegistry
from voteit.messaging.registry import app_state_collectors
from voteit.messaging.registry import collectors_for
from voteit.messaging.state import AppState


class Noop(AppStateCollector):
    name = "test.noop"
    channels = (MeetingChannel,)

    def collect(self, state):
        pass


class RegistryTests(TestCase):
    def _registry(self):
        return CollectorRegistry(AppStateCollector)

    def test_registers_under_its_name(self):
        registry = self._registry()
        registry(Noop)
        self.assertIs(Noop, registry["test.noop"])

    def test_abstract_collector_is_refused(self):
        class Incomplete(AppStateCollector):
            name = "test.incomplete"
            channels = (MeetingChannel,)

        with self.assertRaises(TypeError):
            self._registry()(Incomplete)

    def test_duplicate_name_is_refused(self):
        """A name is part of the wire contract, so a collision must be loud."""

        class Other(Noop):
            pass

        registry = self._registry()
        registry(Noop)
        with self.assertRaises(ImproperlyConfigured):
            registry["test.noop"] = Other

    def test_re_registering_the_same_class_is_fine(self):
        registry = self._registry()
        registry(Noop)
        registry(Noop)
        self.assertEqual(1, len(registry))


class CollectorsForTests(TestCase):
    def test_sorted_by_order_then_name(self):
        for channel in (MeetingChannel, ModeratorsChannel):
            with self.subTest(channel=channel.name):
                found = collectors_for(channel)
                self.assertEqual(sorted(found, key=lambda c: (c.order, c.name)), found)

    def test_registered_on_several_channels(self):
        """agenda.items serves participants and moderators from one class."""
        names = [c.name for c in collectors_for(ModeratorsChannel)]
        self.assertIn("agenda.items", names)

    def test_unknown_channel_has_none(self):
        class Unregistered(MeetingChannel):
            name = "test.nothing.here"

        self.assertEqual([], collectors_for(Unregistered))

    def test_index_is_rebuilt_after_registration(self):
        before = len(collectors_for(MeetingChannel))
        try:
            app_state_collectors(Noop)
            self.assertEqual(before + 1, len(collectors_for(MeetingChannel)))
        finally:
            del app_state_collectors["test.noop"]
            from voteit.messaging.registry import reset_collector_index

            reset_collector_index()
        self.assertEqual(before, len(collectors_for(MeetingChannel)))


class Boom(AppStateCollector):
    name = "test.boom"
    channels = (MeetingChannel,)

    def collect(self, state):
        state.append(InvalidateUserCache(payload={"pk": 1}))
        raise ValueError("nope")


class Fussy(AppStateCollector):
    name = "test.fussy"
    channels = (MeetingChannel,)

    def applicable(self):
        raise ValueError("nope")

    def collect(self, state):  # pragma: no coverage
        raise AssertionError("should never run")


class FailureIsolationTests(TestCase):
    """A broken collector costs its own section, not the whole subscribe."""

    def setUp(self):
        self.meeting = Meeting.objects.create()
        self.channel = MeetingChannel.from_instance(self.meeting)

    def test_failure_marks_the_section_and_keeps_what_it_built(self):
        state = AppState()
        with self.assertLogs("voteit.messaging.jobs", level="ERROR"):
            _collect(Boom(self.channel, None), state)
        self.assertEqual(1, len(state.sections))
        section = state.sections[0]
        self.assertEqual("test.boom", section.name)
        self.assertTrue(section.failed)
        self.assertEqual(1, len(section.messages))

    def test_later_collectors_still_run(self):
        state = AppState()
        with self.assertLogs("voteit.messaging.jobs", level="ERROR"):
            _collect(Boom(self.channel, None), state)
        _collect(Noop(self.channel, None), state)
        self.assertEqual(["test.boom", "test.noop"], [s.name for s in state.sections])

    def test_database_error_is_re_raised(self):
        """No savepoint to recover to, so there is nothing to carry on with."""
        state = AppState()
        with patch("voteit.messaging.jobs.get_connection") as get_conn:
            get_conn.return_value.needs_rollback = True
            with self.assertRaises(ValueError):
                _collect(Boom(self.channel, None), state)

    def test_database_error_in_applicable_is_re_raised(self):
        with patch("voteit.messaging.jobs.get_connection") as get_conn:
            get_conn.return_value.needs_rollback = True
            with self.assertRaises(ValueError):
                _applicable(Fussy(self.channel, None))

    def test_broken_applicable_skips_the_collector(self):
        with self.assertLogs("voteit.messaging.jobs", level="ERROR"):
            self.assertFalse(_applicable(Fussy(self.channel, None)))
