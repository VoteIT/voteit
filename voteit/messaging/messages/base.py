from abc import ABC
from typing import Dict

from pydantic.main import BaseModel
from django.utils.translation import gettext as _
from voteit.core.models import BaseContent

from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.abcs import BaseIncomingMessage
from voteit.messaging.abcs import DeferredJob
from voteit.messaging.abcs import ContextAction
from voteit.messaging.messages.text import TextResponse


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


class BaseObjectAction(BaseIncomingMessage, DeferredJob, ContextAction, ABC):
    pass


class BaseAddObject(BaseObjectAction, ABC):
    schema = GenericObjectSchema
    data: GenericObjectSchema

    def run_job(self):
        self.assert_perm(
            msg=_("You're not allowed to add %(ctype)s here" % {"ctype": self.model})
        )
        if isinstance(self.model, BaseContent):
            self.data.kwargs.setdefault("author", self.user)
        self.model.objects.create(**self.data.kwargs)
        response = TextResponse.from_message(self, message="Added")
        response.send_outgoing(self.mm.consumer_name, success=True)


class BaseChangeObject(BaseObjectAction, ABC):
    schema = GenericObjectSchema
    data: GenericObjectSchema

    def run_job(self):
        self.assert_perm(
            msg=_("You're not allowed to change %(ctype)s here" % {"ctype": self.model})
        )
        self.context.update(**self.data.kwargs)
        self.context.save()
        response = TextResponse.from_message(self, message="Changed")
        response.send_outgoing(self.mm.consumer_name, success=True)


class BaseDeleteObject(BaseObjectAction, ABC):
    # Use default schema with only pk

    def run_job(self):
        self.assert_perm(
            msg=_("You're not allowed to delete %(ctype)s here" % {"ctype": self.model})
        )
        self.context.delete()
        response = TextResponse.from_message(self, message="Deleted")
        response.send_outgoing(self.mm.consumer_name, success=True)
