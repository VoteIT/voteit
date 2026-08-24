from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from django.utils.functional import cached_property
from django.utils.module_loading import import_string
from statemachine import Event
from statemachine import State
from statemachine import StateChart

from voteit.core.signals import after_sm_transition
from voteit.core.signals import before_sm_transition

if TYPE_CHECKING:
    from django.db import models


@lru_cache(maxsize=None)
def load_state_machine(dotted_path: str) -> type[StateChart]:
    """Import a state machine class, once per dotted path.

    Keyed on the path rather than on the model class, so ``DiffProposal``
    shares ``Proposal``'s entry by design rather than by MTI accident.

    ``import_string`` rather than ``statemachine.registry.get_machine_cls``:
    the registry's first call runs ``autodiscover_modules(["statemachine",
    "statemachines"])`` as an import side effect, which we do not want to
    trigger from an arbitrary attribute access. ``core.admin._sm_event_action``
    and ``core.rest_api.mixins.StateMachineMixin`` already resolve this same
    attribute with ``import_string``.
    """
    machine_cls = import_string(dotted_path)
    if not (isinstance(machine_cls, type) and issubclass(machine_cls, StateChart)):
        raise TypeError(
            f"{dotted_path} is not a StateChart subclass, got {machine_cls!r}"
        )
    return machine_cls


class StateMachineModelMixin:
    """Binds a ``python-statemachine`` chart to a model as ``.sm``, lazily.

    Deliberately *not* ``statemachine.mixins.MachineMixin``. That one builds
    the chart inside ``Model.__init__``, so every row a queryset yields pays
    for one: measured at 209 us / 30.8 kB for the cheapest model here
    (MeetingInvite) and 946 us / 143 kB for Poll, against 5.4 us / 584 B for
    the bare model -- 39x the time and 53x the memory, on rows that in almost
    every code path never touch ``.sm`` at all. It also makes ``.only()`` and
    ``.defer()`` unusable on these models: the eager ``getattr(model, "state")``
    hits ``DeferredAttribute``, which calls ``refresh_from_db``, which is one
    extra SELECT per row.

    Building on first access instead is behaviour-preserving because every
    model using this mixin declares a non-null ``state`` with a default, which
    makes ``SyncEngine.start()`` an early return -- construction has never
    activated an initial state or fired an entry callback. The tests in
    ``core.tests.test_statemachine`` pin that invariant so a future
    ``null=True`` cannot quietly break it.

    Caching the chart on the instance is safe because the chart never
    snapshots: ``Configuration.value`` is a live ``getattr(model, "state")`` on
    every read, so a chart built before a ``refresh_from_db()`` or a direct
    ``obj.state = ...`` still reports the current value.

    ``cached_property`` is a non-data descriptor, so it stores into
    ``instance.__dict__`` under exactly the key ``MachineMixin`` used to
    ``setattr``. ``obj.sm``, ``hasattr(obj, "sm")`` and assigning a stub in a
    test all behave as they did.

    Note that a ``__getstate__`` here to keep the cached chart out of pickles
    would be dead code: this mixin is listed last in every model's bases, so
    ``django.db.models.Model`` -- which defines ``__getstate__`` -- precedes it
    in the MRO. It is not needed either; nothing in the project pickles these
    models, and an untouched ``.sm`` now stays out of the pickle by itself.
    """

    state_field_name: str = "state"
    """Name of the model field holding the current state value."""

    state_machine_name: str
    """Dotted path to the chart, e.g. ``"voteit.poll.statemachines.PollStateMachine"``.

    Also read as a plain string by ``core.admin._sm_event_action`` and by
    ``core.rest_api.mixins.StateMachineMixin.get_view_description``.
    """

    @cached_property
    def sm(self) -> StateChart:
        return load_state_machine(self.state_machine_name)(
            self, state_field=self.state_field_name
        )


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
