from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Type, TYPE_CHECKING

from pydantic.main import BaseModel
from django.utils.translation import gettext as _
from voteit.core.models import BaseContent

from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.abcs import BaseIncomingMessage
from voteit.messaging.abcs import DeferredJob
from voteit.messaging.abcs import ContextAction
from voteit.messaging.messages.text import TextResponse

if TYPE_CHECKING:
    from django.db.models import Model


class AddedOrUpdatedSchema(BaseModel):
    pk: int

    class Config:
        extra = "allow"
        arbitrary_types_allowed = True


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


class GenericObjectSchema(BaseModel):
    pk: int  # Context for where this is added
    kwargs: Dict  # What to send to the constructor (create)


class GenericDeleteSchema(BaseModel):
    pk: int


class BaseObjectAction(BaseIncomingMessage, DeferredJob, ContextAction, ABC):
    pass


class BaseAddObject(BaseObjectAction, ABC):
    schema = GenericObjectSchema
    data: GenericObjectSchema

    @property
    @abstractmethod
    def add_model(self) -> Type[Model]:
        """The model used for creation of the added object.
        note that cls.model is the context where it will be added.
        """

    @property
    @abstractmethod
    def relation_queryset_attribute(self):
        """Where on the context we want create the new object.
        For instance, on agenda items the relation has the name 'proposals'
        """

    def run_job(self):
        self.assert_perm(
            msg=_("You're not allowed to add %(ctype)s here")
            % {"ctype": self.add_model}
        )

        if issubclass(self.add_model, BaseContent):
            self.data.kwargs.setdefault("author", self.user)
        relation = getattr(self.context, self.relation_queryset_attribute)
        relation.create(**self.data.kwargs)
        response = TextResponse.from_message(self, msg="Added")
        response.send_outgoing(self.mm.consumer_name, success=True)


class BaseChangeObject(BaseObjectAction, ABC):
    schema = GenericObjectSchema
    data: GenericObjectSchema

    def run_job(self):
        self.assert_perm(
            msg=_("You're not allowed to change %(ctype)s here" % {"ctype": self.model})
        )
        # self.context.update(**self.data.kwargs)
        # FIXME This should be validated and saved using a serializer
        for key, value in self.data.kwargs.items():
            setattr(self.context, key, value)
        self.context.save()
        response = TextResponse.from_message(self, msg="Changed")
        response.send_outgoing(self.mm.consumer_name, success=True)


class BaseDeleteObject(BaseObjectAction, ABC):
    schema = GenericDeleteSchema
    data: GenericDeleteSchema

    def run_job(self):
        self.assert_perm(
            msg=_("You're not allowed to delete %(ctype)s here" % {"ctype": self.model})
        )
        self.context.delete()
        response = TextResponse.from_message(self, msg="Deleted")
        response.send_outgoing(self.mm.consumer_name, success=True)
