from __future__ import annotations

from collections import UserList
from collections.abc import Iterable
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import field

from chanx.messages.base import BaseMessage

from voteit.messaging.registry import batch_for


@dataclass
class StateSection:
    """One collector's contribution, kept apart so it can be named on the wire."""

    name: str
    messages: list[BaseMessage] = field(default_factory=list)
    #: The collector raised. Its messages, if any, are still worth sending.
    failed: bool = False


class AppState(UserList):
    """Accumulator for the messages that make up a channel's initial state.

    Iterating an ``AppState`` yields every message in the order it was added,
    whichever collector produced it -- that flat view is what most tests assert
    on. :attr:`sections` is the same messages grouped by collector, which is
    what the subscribe job bundles up.

    >>> from voteit.core.messages.user import InvalidateUserCache
    >>> state = AppState()
    >>> with state.section("demo.one"):
    ...     state.append(InvalidateUserCache(payload={"pk": 1}))
    >>> with state.section("demo.two"):
    ...     state.append(InvalidateUserCache(payload={"pk": 2}))
    >>> len(state)
    2
    >>> [(s.name, len(s.messages)) for s in state.sections]
    [('demo.one', 1), ('demo.two', 1)]

    Appending outside a section still works -- a collector called directly from
    a test has nowhere to put its name -- the message just isn't in any section.

    >>> state = AppState()
    >>> state.append(InvalidateUserCache(payload={"pk": 3}))
    >>> len(state), state.sections
    (1, [])
    """

    def __init__(self, initlist=None):
        self.sections: list[StateSection] = []
        self._current: StateSection | None = None
        super().__init__(initlist)

    @contextmanager
    def section(self, name: str) -> Iterator[StateSection]:
        """Tag everything appended inside the block as belonging to ``name``.

        The section is created up front and kept even if the block raises, so a
        collector that fails halfway still delivers what it managed to build.
        """
        if self._current is not None:  # pragma: no coverage
            raise RuntimeError(
                f"Cannot open section {name!r} inside {self._current.name!r}"
            )
        current = StateSection(name)
        self.sections.append(current)
        self._current = current
        try:
            yield current
        finally:
            self._current = None

    def append(self, item: BaseMessage) -> None:
        if not isinstance(item, BaseMessage):
            raise TypeError(f"Expected a BaseMessage, got {type(item).__name__}")
        super().append(item)
        if self._current is not None:
            self._current.messages.append(item)

    def add_batch(self, message_cls: type[BaseMessage], payloads: Iterable) -> None:
        """Append one ``<action>.batch`` message, or nothing if empty.

        Initial state is almost always many payloads of the same type, so this
        is the usual way for a collector to contribute.
        """
        items = list(payloads)
        if items:
            self.append(batch_for(message_cls)(payload={"items": items}))
