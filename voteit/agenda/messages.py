from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from pydantic import validator
from envelope.core.message import ContextAction
from envelope.core.message import Message
from envelope.utils import websocket_send
from django.utils import timezone

from voteit.agenda.models import AgendaItem
from voteit.agenda.permissions import AgendaPermissions
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted


# This should probably not exist since we use the rest interface.
# @incoming
# class AddAgendaItem(BaseAddObject):
#     name = "agenda_item.add"
#     permission = AgendaPermissions.ADD
#     model = Meeting  # This is the context for the action!
#     add_model = AgendaItem
#     relation_queryset_attribute = "agenda_items"
#
#
# @incoming
# class ChangeAgendaItem(BaseChangeObject):
#     name = "agenda_item.change"
#     model = AgendaItem
#     permission = AgendaPermissions.CHANGE
#
#
# @incoming
# class DeleteAgendaItem(BaseDeleteObject):
#     name = "agenda_item.delete"
#     model = AgendaItem
#     permission = AgendaPermissions.DELETE


class UpdateLastReadSchema(BaseModel):
    agenda_item: int


@incoming
class UpdateLastRead(ContextAction):
    name = "last_read.change"
    model = AgendaItem
    context: AgendaItem
    context_schema_attr = "agenda_item"
    permission = AgendaPermissions.VIEW  # FIXME: Anon users and public meetings?
    schema = UpdateLastReadSchema
    data: UpdateLastReadSchema

    def run_job(self) -> LastReadChanged:
        """
        Create or mark agenda as read. This will create a separate database entry,
        but we'll serialize the agenda item instead.
        """
        self.assert_perm()
        timestamp = self.context.mark_read(self.user)
        response = LastReadChanged.from_message(
            self, timestamp=timestamp, agenda_item=self.context.pk
        )
        websocket_send(response, state=response.SUCCESS)
        return response


@outgoing
class AgendaAdded(BaseObjectAdded):
    name = "agenda_item.added"


@outgoing
class AgendaChanged(BaseObjectChanged):
    name = "agenda_item.changed"


@outgoing
class AgendaDeleted(BaseObjectDeleted):
    name = "agenda_item.deleted"


class LastReadChangedSchema(BaseModel):
    """
    >>> from django.utils.timezone import now
    >>> one=LastReadChangedSchema(agenda_item=1, timestamp=now())
    >>> isinstance(one.timestamp, str)
    True
    """

    timestamp: str
    agenda_item: int

    @validator("timestamp", pre=True)
    def convert_dt(cls, v):
        if isinstance(v, datetime):
            tz = timezone.get_current_timezone()
            v = v.astimezone(tz)
            return v.isoformat()
        return v


@outgoing
class LastReadChanged(Message):
    name = "last_read.changed"
    schema = LastReadChangedSchema
    data: LastReadChangedSchema
