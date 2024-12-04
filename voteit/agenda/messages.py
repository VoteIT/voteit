from __future__ import annotations

from datetime import datetime
from logging import getLogger

from django.utils import timezone
from envelope.core.message import Message
from envelope.deferred_jobs.message import ContextAction
from envelope.utils import websocket_send
from pydantic import BaseModel
from pydantic import conlist
from pydantic import root_validator
from pydantic import validator
from rest_framework.exceptions import ValidationError

from voteit.agenda.models import AgendaItem
from voteit.agenda.permissions import AgendaPermissions
from voteit.core.rest_api.utils import drf_do_transition
from voteit.core.rest_api.utils import get_valid_transitions
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing

logger = getLogger(__name__)


class AgendaItemBulkChangeSchema(BaseModel):
    meeting: int
    state: str | None = None
    block_discussion: bool | None = None
    block_proposals: bool | None = None
    # Agenda items validated in message to avoid loading models
    agenda_items: conlist(int, min_items=1, unique_items=True)

    @root_validator
    def do_something(cls, values):
        """
        >>> f = AgendaItemBulkChangeSchema.do_something
        >>> data = {'state': None, 'block_discussion': True, 'block_proposals': None}
        >>> f(data) == data
        True
        >>> data['block_discussion'] = None
        >>> f(data)
        Traceback (most recent call last):
        ...
        ValueError: state, block_discussion or block_proposals required
        """
        if all(
            values.get(x) is None
            for x in ("state", "block_discussion", "block_proposals")
        ):
            raise ValueError("state, block_discussion or block_proposals required")
        return values


@incoming
class AgendaItemBulkChange(ContextAction):
    name = "agenda_item.bulk_update"
    model = Meeting
    schema = AgendaItemBulkChangeSchema
    data: AgendaItemBulkChangeSchema
    context: Meeting
    context_schema_attr = "meeting"
    permission = MeetingPermissions.CHANGE
    ttl: 20

    def run_job(self):
        self.assert_perm()
        agenda_items = list(
            self.context.agenda_items.filter(pk__in=self.data.agenda_items)
        )
        must_save = set()
        # Remember! We can't reload or change queryset when we touch several attributes.
        if self.data.state:
            for ai in agenda_items:
                if ai == self.data.state:
                    continue
                for transition in get_valid_transitions(ai):
                    if transition.target == self.data.state:
                        try:
                            drf_do_transition(
                                instance=ai,
                                transition_name=transition.name,
                                valid_transitions={
                                    transition.name: transition
                                },  # We're cheating here
                                user=self.user,
                            )
                            must_save.add(ai)
                        except ValidationError as exc:
                            logger.debug("Transition failed", exc_info=True)
                        break
        if self.data.block_proposals is not None:
            for ai in agenda_items:
                if ai.block_proposals != self.data.block_proposals:
                    ai.block_proposals = self.data.block_proposals
                    must_save.add(ai)
        if self.data.block_discussion is not None:
            for ai in agenda_items:
                if ai.block_discussion != self.data.block_discussion:
                    ai.block_discussion = self.data.block_discussion
                    must_save.add(ai)
        for ai in must_save:
            ai.save()


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
    ttl = 15

    def run_job(self):
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


@outgoing
class AgendaAdded(BaseObjectAdded):
    name = "agenda_item.added"


@outgoing
class AgendaChanged(BaseObjectChanged):
    name = "agenda_item.changed"


@outgoing
class AgendaDeleted(BaseObjectDeleted):
    name = "agenda_item.deleted"


@outgoing
class AgendaBodyAdded(BaseObjectAdded):
    name = "agenda_body.added"


@outgoing
class AgendaBodyChanged(BaseObjectChanged):
    name = "agenda_body.changed"


@outgoing
class AgendaBodyDeleted(BaseObjectDeleted):
    name = "agenda_body.deleted"


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
