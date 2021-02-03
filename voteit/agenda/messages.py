from __future__ import annotations
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model

from voteit.agenda.models import AgendaItem
from voteit.agenda.permissions import AgendaPermissions
from voteit.messaging.decorators import outgoing, incoming
from voteit.messaging.messages.base import (
    BaseObjectAdded,
    BaseObjectChanged,
    BaseObjectDeleted,
    BaseAddObject,
    BaseChangeObject,
    BaseDeleteObject,
)
from voteit.meeting.models import Meeting

User = get_user_model()


if TYPE_CHECKING:
    pass


@incoming
class AddAgendaItem(BaseAddObject):
    name = "agenda.add"
    permission = AgendaPermissions.ADD
    model = Meeting  # This is the context for the action!
    add_model = AgendaItem
    relation_queryset_attribute = "agenda_items"


@incoming
class ChangeAgendaItem(BaseChangeObject):
    name = "agenda.change"
    model = AgendaItem
    permission = AgendaPermissions.CHANGE


@incoming
class DeleteAgendaItem(BaseDeleteObject):
    name = "agenda.delete"
    model = AgendaItem
    permission = AgendaPermissions.DELETE


@outgoing
class AgendaAdded(BaseObjectAdded):
    name = "agenda.added"


@outgoing
class AgendaChanged(BaseObjectChanged):
    name = "agenda.changed"


@outgoing
class AgendaDeleted(BaseObjectDeleted):
    name = "agenda.deleted"
