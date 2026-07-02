from __future__ import annotations

from datetime import datetime

from django.utils import timezone
from envelope.core.message import Message
from pydantic import BaseModel
from pydantic import validator

from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import outgoing


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
