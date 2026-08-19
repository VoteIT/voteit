from __future__ import annotations

from datetime import datetime

from django.utils import timezone
from pydantic import validator
from pydantic.main import BaseModel

from envelope.core.message import Message


class AddedOrUpdatedSchema(BaseModel):
    pk: int

    class Config:
        extra = "allow"
        arbitrary_types_allowed = True

    @validator(
        "created",
        "modified",
        "timestamp",
        pre=True,
        check_fields=False,
    )
    def convert_dt(cls, v):
        """
        Note! This validator isn't run unless the field is defined on the model!
        """
        if isinstance(v, datetime):
            tz = timezone.get_current_timezone()
            v = v.astimezone(tz)
            return v.isoformat()
        return v


class DeletedSchema(BaseModel):
    pk: int


class BaseObjectAdded(Message):
    schema = AddedOrUpdatedSchema
    data: AddedOrUpdatedSchema


class BaseObjectChanged(Message):
    schema = AddedOrUpdatedSchema
    data: AddedOrUpdatedSchema


class BaseObjectDeleted(Message):
    schema = DeletedSchema
    data: DeletedSchema
