from __future__ import annotations

from typing import TYPE_CHECKING

from statemachine import Event
from statemachine import State

from voteit.core.signals import after_sm_transition
from voteit.core.signals import before_sm_transition

if TYPE_CHECKING:
    from django.db import models


class TransitionSignalMixin:
    model: models.Model

    def before_transition(self, source: State, target: State, event: Event, **kwargs):
        return before_sm_transition.send(
            sender=self.model.__class__,
            instance=self.model,
            source=source,
            target=target,
            event=event,
            **kwargs,
        )

    def after_transition(self, source: State, target: State, event: Event, **kwargs):
        return after_sm_transition.send(
            sender=self.model.__class__,
            instance=self.model,
            source=source,
            target=target,
            event=event,
            **kwargs,
        )
