from __future__ import annotations

from unittest.mock import patch

import statemachine.registry as sm_registry
from django.test import TestCase
from statemachine import Event
from statemachine import State
from statemachine import StateChart

from voteit.core.signals import after_sm_transition
from voteit.core.signals import before_sm_transition
from voteit.core.statemachines import TransitionSignalMixin


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
