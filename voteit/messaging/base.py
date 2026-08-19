from __future__ import annotations

from abc import ABC
from datetime import datetime

from chanx.messages.base import BaseMessage
from django.utils import timezone
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import model_validator


class AddedOrUpdatedSchema(BaseModel):
    """Payload for object add/change messages.

    Deliberately permissive: publishers hand it whatever their DRF serializer
    or ``.values()`` query produced, and the frontend upserts on ``pk``.
    """

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    pk: int

    @model_validator(mode="before")
    @classmethod
    def isoformat_datetimes(cls, data):
        """Render every datetime in the local timezone, declared or extra.

        Under pydantic v1 this was a field validator naming created/modified/
        timestamp with check_fields=False, so it only covered those three and
        only when a subclass declared them; extras were left to pydantic's own
        encoder. v2 serialises extra datetimes as UTC with a Z suffix, which
        would silently change the wire format for the publishers that pass
        .values() output rather than serializer output. Normalising every
        datetime here keeps one format and drops the check_fields footgun.

        >>> from datetime import datetime, timezone as dt_timezone
        >>> dt = datetime(2020, 1, 1, tzinfo=dt_timezone.utc)
        >>> AddedOrUpdatedSchema(pk=1, seen=dt).model_dump()["seen"]
        '2020-01-01T01:00:00+01:00'
        """
        if not isinstance(data, dict):
            return data
        tz = timezone.get_current_timezone()
        return {
            key: value.astimezone(tz).isoformat()
            if isinstance(value, datetime)
            else value
            for key, value in data.items()
        }


class DeletedSchema(BaseModel):
    pk: int


class ObjectAddedOrChanged(BaseMessage, ABC):
    """An object was created or updated. The client upserts on pk.

    There is no separate "added" message -- see the CHANGELOG.
    """

    payload: AddedOrUpdatedSchema


class ObjectDeleted(BaseMessage, ABC):
    payload: DeletedSchema
