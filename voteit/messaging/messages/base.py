from typing import Dict

from pydantic.main import BaseModel

from voteit.messaging.abcs import BaseOutgoingMessage


class AddedOrUpdatedSchema(BaseModel):
    item: Dict


class DeletedSchema(BaseModel):
    pk: int


class BaseObjectAdded(BaseOutgoingMessage):
    schema = AddedOrUpdatedSchema
    data: AddedOrUpdatedSchema


class BaseObjectChanged(BaseOutgoingMessage):
    schema = AddedOrUpdatedSchema
    data: AddedOrUpdatedSchema


class BaseObjectDeleted(BaseOutgoingMessage):
    schema = DeletedSchema
    data: DeletedSchema
