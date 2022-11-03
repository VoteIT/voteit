from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING

from pydantic.main import BaseModel

from envelope.core.message import ContextAction
from envelope.core.message import Message
from envelope.messages.common import Status
from envelope.utils import websocket_send
from voteit.core.models import BaseContent

if TYPE_CHECKING:
    from django.db.models import Model


class AddedOrUpdatedSchema(BaseModel):
    pk: int

    class Config:
        extra = "allow"
        arbitrary_types_allowed = True


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


class GenericObjectSchema(BaseModel):
    pk: int  # Context for where this is added
    kwargs: dict  # What to send to the constructor (create)


class GenericDeleteSchema(BaseModel):
    pk: int


class BaseObjectAction(ContextAction, ABC):
    ...


class BaseAddObject(BaseObjectAction, ABC):
    schema = GenericObjectSchema
    data: GenericObjectSchema

    @property
    @abstractmethod
    def add_model(self) -> type[Model]:
        """The model used for creation of the added object.
        note that cls.model is the context where it will be added.
        """

    @property
    @abstractmethod
    def relation_queryset_attribute(self):
        """Where on the context we want create the new object.
        For instance, on agenda items the relation has the name 'proposals'
        """

    def run_job(self) -> Status:
        self.assert_perm()
        if issubclass(self.add_model, BaseContent):
            self.data.kwargs.setdefault("author", self.user)
        relation = getattr(self.context, self.relation_queryset_attribute)
        relation.create(**self.data.kwargs)
        response = Status.from_message(self)
        websocket_send(response, state=response.SUCCESS)
        return response


class BaseChangeObject(BaseObjectAction, ABC):
    schema = GenericObjectSchema
    data: GenericObjectSchema

    def run_job(self) -> Status:
        self.assert_perm()
        # self.context.update(**self.data.kwargs)
        # FIXME This should be validated and saved using a serializer
        for key, value in self.data.kwargs.items():
            setattr(self.context, key, value)
        self.context.save()
        response = Status.from_message(self)
        websocket_send(response, state=response.SUCCESS)
        return response


class BaseDeleteObject(BaseObjectAction, ABC):
    schema = GenericDeleteSchema
    data: GenericDeleteSchema

    def run_job(self) -> Status:
        self.assert_perm()
        self.context.delete()
        response = Status.from_message(self, msg="Deleted")
        websocket_send(response, state=response.SUCCESS)
        return response
