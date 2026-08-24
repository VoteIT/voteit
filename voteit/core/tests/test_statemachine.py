from __future__ import annotations

from unittest.mock import patch

import statemachine.registry as sm_registry
from django.apps import apps
from django.db.models import NOT_PROVIDED
from django.test import TestCase
from statemachine import Event
from statemachine import State
from statemachine import StateChart

from voteit.core.signals import after_sm_transition
from voteit.core.signals import before_sm_transition
from voteit.core.statemachines import StateMachineModelMixin
from voteit.core.statemachines import TransitionSignalMixin


def sm_models():
    """Every concrete model that binds a state machine."""
    return [m for m in apps.get_models() if issubclass(m, StateMachineModelMixin)]


class DummyModel:
    pass


class TransitionSignalMixinTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with patch.object(sm_registry, "_REGISTRY", {}):

            class DummyStateMachine(StateChart, TransitionSignalMixin):
                idle = State(value="idle", initial=True)
                running = State(value="running")
                done = State(value="done", final=True)

                start = Event(idle.to(running))
                finish = Event(running.to(done))

            cls.DummyStateMachine = DummyStateMachine

    def setUp(self):
        self.model = DummyModel()
        self.sm = self.DummyStateMachine(model=self.model)

    @staticmethod
    def _collect(signal):
        received = []
        signal.connect(lambda sender, **kw: received.append((sender, kw)), weak=False)
        return received

    def test_before_transition_fires(self):
        received = self._collect(before_sm_transition)
        try:
            self.sm.start()
            self.assertEqual(len(received), 1)
        finally:
            before_sm_transition.disconnect()

    def test_after_transition_fires(self):
        received = self._collect(after_sm_transition)
        try:
            self.sm.start()
            self.assertEqual(len(received), 1)
        finally:
            after_sm_transition.disconnect()

    def test_sender_is_model_class(self):
        received = self._collect(before_sm_transition)
        try:
            self.sm.start()
            sender, _ = received[0]
            self.assertIs(sender, DummyModel)
        finally:
            before_sm_transition.disconnect()

    def test_instance_is_model(self):
        received = self._collect(after_sm_transition)
        try:
            self.sm.start()
            _, kw = received[0]
            self.assertIs(kw["instance"], self.model)
        finally:
            after_sm_transition.disconnect()

    def test_signal_carries_source_target_event(self):
        received = self._collect(after_sm_transition)
        try:
            self.sm.start()
            _, kw = received[0]
            self.assertEqual(kw["source"].id, "idle")
            self.assertEqual(kw["target"].id, "running")
            self.assertEqual(kw["event"].id, "start")
        finally:
            after_sm_transition.disconnect()

    def test_both_signals_fire_per_transition(self):
        before = self._collect(before_sm_transition)
        after = self._collect(after_sm_transition)
        try:
            self.sm.start()
            self.sm.finish()
            self.assertEqual(len(before), 2)
            self.assertEqual(len(after), 2)
        finally:
            before_sm_transition.disconnect()
            after_sm_transition.disconnect()


class StateMachineModelMixinTests(TestCase):
    """The lazy ``.sm`` binding, and the invariants that make it equivalent.

    ``StateMachineModelMixin`` replaced ``statemachine.mixins.MachineMixin``,
    which built a chart inside every ``Model.__init__`` -- 209 us / 30.8 kB per
    MeetingInvite, 946 us / 143 kB per Poll, on every row of every queryset.
    """

    EXPECTED = {
        "AgendaItem",
        "DiffProposal",
        "Meeting",
        "MeetingInvite",
        "Poll",
        "Proposal",
        "SpeakerListSystem",
    }

    def test_state_default_is_never_none(self):
        """The invariant that licenses laziness.

        ``SyncEngine.start()`` early-returns when ``current_state_value`` is
        not None, so with a non-null default the eager mixin never activated an
        initial state at construction either. Give ``state`` a null default and
        that stops being true -- entry callbacks would start firing from a new
        place, and this test is what says so.
        """
        for model in sm_models():
            with self.subTest(model=model.__name__):
                field = model._meta.get_field(model.state_field_name)
                self.assertFalse(field.null, f"{model.__name__}.state is nullable")
                self.assertIsNot(field.default, NOT_PROVIDED)
                self.assertIsNotNone(field.default)

    def test_mixin_is_applied_to_the_expected_models(self):
        """Catches a model losing the mixin, or gaining it without review."""
        self.assertEqual({m.__name__ for m in sm_models()}, self.EXPECTED)

    def test_state_machine_attr_is_not_used(self):
        """``state_machine_attr`` was an upstream hook; we hardcode ``sm``.

        A leftover ``state_machine_attr = "workflow"`` would now be silently
        ignored rather than renaming the attribute, so fail on it here.
        """
        for model in sm_models():
            with self.subTest(model=model.__name__):
                self.assertFalse(hasattr(model, "state_machine_attr"))

    def test_every_state_machine_resolves(self):
        """Restores the fail-fast the eager mixin gave for a bad dotted path."""
        for model in sm_models():
            with self.subTest(model=model.__name__):
                sm = model().sm
                self.assertIs(sm.model.__class__, model)
                self.assertEqual(
                    model._meta.get_field(model.state_field_name).default,
                    sm.current_state_value,
                )

    def test_construction_builds_no_state_machine(self):
        for model in sm_models():
            with self.subTest(model=model.__name__):
                self.assertNotIn("sm", model().__dict__)

    def test_iterating_a_queryset_builds_no_state_machines(self):
        meeting = self._meeting()
        for obj in type(meeting).objects.filter(pk=meeting.pk):
            self.assertNotIn("sm", obj.__dict__)

    def test_deferred_queryset_does_not_query_per_row(self):
        """``.only()`` used to cost one extra SELECT per row.

        The eager chart read ``model.state`` during ``__init__``; on a deferred
        instance that is a ``DeferredAttribute``, so it called
        ``refresh_from_db`` once per row.

        Uses MeetingInvite because ``Meeting.__init__`` and
        ``SpeakerListSystem.__init__`` snapshot other fields for change
        detection and so still trigger a refresh under ``.only()`` -- a
        separate issue from the state machine, and untouched here.
        """
        from voteit.invites.models import MeetingInvite

        meeting = self._meeting()
        for i in range(3):
            MeetingInvite.objects.create(
                meeting=meeting, user_data={"email": f"a{i}@example.com"}
            )
        with self.assertNumQueries(1):
            list(MeetingInvite.objects.only("pk").filter(meeting=meeting))

    def test_cached_machine_reads_state_live(self):
        """Caching is safe: ``Configuration.value`` is a live ``getattr``."""
        meeting = self._meeting()
        sm = meeting.sm
        other = next(s for s in sm.states if s.value != meeting.state and not s.final)
        meeting.state = other.value
        self.assertEqual(sm.current_state_value, other.value)
        self.assertIs(meeting.sm, sm)

    def test_cached_machine_follows_refresh_from_db(self):
        meeting = self._meeting()
        sm = meeting.sm
        original = meeting.state
        type(meeting).objects.filter(pk=meeting.pk).update(state="ongoing")
        meeting.refresh_from_db()
        self.assertNotEqual(original, "ongoing")
        self.assertEqual(sm.current_state_value, "ongoing")

    def test_construction_does_not_fire_transition_signals(self):
        received = []
        after_sm_transition.connect(
            lambda sender, **kw: received.append(kw), weak=False
        )
        try:
            for model in sm_models():
                model().sm
            self.assertEqual(received, [])
        finally:
            after_sm_transition.disconnect()

    def _meeting(self):
        from voteit.meeting.models import Meeting
        from voteit.organisation.models import Organisation

        org = Organisation.objects.create(title="Org", host="sm.example.com")
        return Meeting.objects.create(organisation=org, title="Meeting")
