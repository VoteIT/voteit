from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count

from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.agenda.channels import AgendaItemChannel
from voteit.core.utils import get_model_shortname
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors
from voteit.messaging.values import wire_values
from voteit.reactions.messages import ButtonChanged
from voteit.reactions.messages import ReactionCount
from voteit.reactions.messages import UserReactionChanged
from voteit.reactions.rest_api.serializers import ButtonDetailSerializer
from voteit.reactions.rest_api.serializers import ReactionSerializer

if TYPE_CHECKING:
    from collections.abc import Iterator

    from django.db.models import QuerySet

    from voteit.messaging.state import AppState


def content_type_shortname(pk: int) -> str:
    """The model shortname the wire uses for a content type pk.

    ``ContentType.objects.get_for_id`` is cached per process, so this is free
    after the first call for a given type. Going through the FK descriptor
    instead is not: it issues a plain SELECT per access, which is what made
    ``reactions.own`` cost one query per reaction.
    """
    return get_model_shortname(ContentType.objects.get_for_id(pk).model_class())


def button_payloads(qs: QuerySet) -> QuerySet:
    """The ``reaction_button.changed`` payload for every button in ``qs``.

    ``.values()`` rather than ButtonDetailSerializer, which is sixteen plain
    columns and no method fields. ``change_roles`` and ``list_roles`` are
    declared RolesFields, but those are ListFields of CharFields over
    ArrayField columns and render the same list either way.
    """
    return wire_values(ButtonDetailSerializer, qs)


def reaction_payloads(qs: QuerySet) -> Iterator[dict]:
    """The ``reaction.changed`` payload for every reaction in ``qs``.

    ``.values()`` here is not a tuning choice. ``ReactionSerializer`` renders
    ``content_type`` with a CharField subclass, so it gets none of DRF's
    pk-only optimisation and loads a ContentType per row: 132 queries and
    44.8 ms for the 131 reactions one user holds on the busiest agenda item in
    the dev data, against one query and 0.6 ms here. The mapping is the same
    one ``ReactionCounts`` does, and is mandatory rather than cosmetic --
    ``UserReactionResponseSchema.content_type`` is a validated shortname, so a
    raw pk would be rejected rather than sent.
    """
    for row in wire_values(ReactionSerializer, qs):
        row["content_type"] = content_type_shortname(row["content_type"])
        yield row


@app_state_collectors
class ReactionButtons(AppStateCollector):
    name = "reactions.buttons"
    channels = (ParticipantsChannel, ModeratorsChannel)
    order = 40

    def collect(self, state: AppState) -> None:
        state.add_batch(
            ButtonChanged, button_payloads(self.context.reaction_buttons.all())
        )


@app_state_collectors
class ReactionCounts(AppStateCollector):
    """How many reactions each button has on each object in this item."""

    name = "reactions.counts"
    channels = (AgendaItemChannel,)
    order = 60

    def collect(self, state: AppState) -> None:
        payloads = []
        for button in (
            self.context.reactions.values("content_type", "object_id", "button")
            .annotate(count=Count("pk"))
            .order_by()
        ):
            button["content_type"] = content_type_shortname(button["content_type"])
            payloads.append(button)
        state.add_batch(ReactionCount, payloads)


@app_state_collectors
class OwnReactions(AppStateCollector):
    """The subscriber's own reactions within this agenda item."""

    name = "reactions.own"
    channels = (AgendaItemChannel,)
    order = 200

    def collect(self, state: AppState) -> None:
        state.add_batch(
            UserReactionChanged,
            reaction_payloads(self.context.reactions.filter(user=self.user)),
        )
