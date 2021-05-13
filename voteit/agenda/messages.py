from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from voteit.agenda.models import AgendaItem
from voteit.agenda.permissions import AgendaPermissions
from voteit.agenda.rest_api.serializers import AgendaItemSerializer
from voteit.meeting.models import Meeting
from voteit.messaging.abcs import BaseIncomingMessage
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.abcs import ContextAction
from voteit.messaging.abcs import DeferredJob
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.messaging.messages.base import BaseAddObject
from voteit.messaging.messages.base import BaseChangeObject
from voteit.messaging.messages.base import BaseDeleteObject
from voteit.messaging.messages.base import BaseObjectAdded
from voteit.messaging.messages.base import BaseObjectChanged
from voteit.messaging.messages.base import BaseObjectDeleted


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


class UpdateLastReadSchema(BaseModel):
    agenda_item: int


@incoming
class UpdateLastRead(BaseIncomingMessage, DeferredJob, ContextAction):
    name = "last_read.change"
    model = AgendaItem
    context: AgendaItem
    context_pk_attr = "agenda_item"
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
        response.send_outgoing(self.mm.consumer_name, success=True)
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
    timestamp: datetime
    agenda_item: int


@outgoing
class LastReadChanged(BaseOutgoingMessage):
    name = "last_read.changed"
    schema = LastReadChangedSchema
    data: LastReadChangedSchema
