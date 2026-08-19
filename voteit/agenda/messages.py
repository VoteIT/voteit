from __future__ import annotations

from typing import Literal
from chanx.messages.base import BaseMessage

from datetime import datetime

from django.utils import timezone
from pydantic import BaseModel
from pydantic import field_validator

from voteit.messaging.base import ObjectAddedOrChanged
from voteit.messaging.base import ObjectDeleted
from voteit.messaging.decorators import outgoing


@outgoing
class AgendaChanged(ObjectAddedOrChanged):
    action: Literal["agenda_item.changed"] = "agenda_item.changed"


@outgoing
class AgendaDeleted(ObjectDeleted):
    action: Literal["agenda_item.deleted"] = "agenda_item.deleted"


@outgoing
class AgendaBodyChanged(ObjectAddedOrChanged):
    action: Literal["agenda_body.changed"] = "agenda_body.changed"


@outgoing
class AgendaBodyDeleted(ObjectDeleted):
    action: Literal["agenda_body.deleted"] = "agenda_body.deleted"


class LastReadChangedSchema(BaseModel):
    """
    >>> from django.utils.timezone import now
    >>> one=LastReadChangedSchema(agenda_item=1, timestamp=now())
    >>> isinstance(one.timestamp, str)
    True
    """

    timestamp: str
    agenda_item: int

    @field_validator("timestamp", mode="before")
    @classmethod
    def convert_dt(cls, v):
        if isinstance(v, datetime):
            tz = timezone.get_current_timezone()
            v = v.astimezone(tz)
            return v.isoformat()
        return v


@outgoing
class LastReadChanged(BaseMessage):
    action: Literal["last_read.changed"] = "last_read.changed"
    payload: LastReadChangedSchema
