from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model

from voteit.agenda.models import AgendaItem
from voteit.agenda.permissions import AgendaPermissions
from voteit.meeting.models import Meeting
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.messaging.messages.base import BaseAddObject
from voteit.messaging.messages.base import BaseChangeObject
from voteit.messaging.messages.base import BaseDeleteObject
from voteit.messaging.messages.base import BaseObjectAdded
from voteit.messaging.messages.base import BaseObjectChanged
from voteit.messaging.messages.base import BaseObjectDeleted

User = get_user_model()


if TYPE_CHECKING:
    pass


@incoming
class AddAgendaItem(BaseAddObject):
    name = "agenda_item.add"
    permission = AgendaPermissions.ADD
    model = Meeting  # This is the context for the action!
    add_model = AgendaItem
    relation_queryset_attribute = "agenda_items"


@incoming
class ChangeAgendaItem(BaseChangeObject):
    name = "agenda_item.change"
    model = AgendaItem
    permission = AgendaPermissions.CHANGE


@incoming
class DeleteAgendaItem(BaseDeleteObject):
    name = "agenda_item.delete"
    model = AgendaItem
    permission = AgendaPermissions.DELETE


@outgoing
class AgendaAdded(BaseObjectAdded):
    name = "agenda_item.added"


@outgoing
class AgendaChanged(BaseObjectChanged):
    name = "agenda_item.changed"


@outgoing
class AgendaDeleted(BaseObjectDeleted):
    name = "agenda_item.deleted"
