"""Named contributors to a channel's initial state.

A collector is the successor to a ``channel_subscribed`` receiver. The signal
gave a receiver no identity: the client saw an undifferentiated run of messages
between ``channel.subscribed`` and ``channel.state_complete`` and could not tell
what was still coming. A collector has a name, which is announced up front and
repeated on every section it produces, an explicit order, and a cheap
``applicable()`` guess so a feature that is switched off is never announced at
all.

Declare one per ``collectors.py`` module in the owning app; ``MessagingConfig``
autodiscovers them.
"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.db import models

    from voteit.messaging.channels import ContextChannel
    from voteit.messaging.state import AppState


class AppStateCollector(ABC):
    """Contributes one named section of a channel's initial state.

    Instantiated once per subscribe, per channel it is registered for. Anything
    expensive belongs in :meth:`collect`; ``__init__`` and :meth:`applicable`
    run for every subscriber whether or not the section is wanted.
    """

    #: Lower runs first, ties broken by name. 10 structural, 50 content,
    #: 100 default, 200 user-specific.
    order: int = 100

    @property
    @abstractmethod
    def name(self) -> str:
        """Registry key, and what the client sees. Convention: ``<app>.<what>``."""

    @property
    @abstractmethod
    def channels(self) -> tuple[type[ContextChannel], ...]:
        """The channels this collector runs for."""

    def __init__(self, channel: ContextChannel, user):
        self.channel = channel
        self.user = user

    def __repr__(self) -> str:  # pragma: no coverage
        return f"<{type(self).__name__} {self.name!r}>"

    @property
    def context(self) -> models.Model:
        """The object the channel is about. Already loaded by the subscribe job."""
        return self.channel.context

    def applicable(self) -> bool:
        """Cheap guess at whether this collector has anything to say.

        False means it is skipped *and* left out of the ``collectors`` list on
        ``channel.subscribed``, so the client never waits for it. Keep this to
        an attribute read or a single indexed query -- it runs on every
        subscribe. Returning True and then collecting nothing is fine; the
        section is simply empty.
        """
        return True

    @abstractmethod
    def collect(self, state: AppState) -> None:
        """Append messages for this section to ``state``."""
