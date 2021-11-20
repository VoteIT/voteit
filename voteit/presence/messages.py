from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext as _
from pydantic.main import BaseModel

from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.messaging.errors import ValidationErrorMsg
from voteit.messaging.messages.base import BaseAddObject
from voteit.messaging.messages.base import BaseDeleteObject
from voteit.messaging.messages.base import BaseObjectAdded
from voteit.messaging.messages.base import BaseObjectChanged
from voteit.messaging.messages.base import BaseObjectDeleted
from voteit.messaging.messages.status import StatusDone
from voteit.presence.models import Presence
from voteit.presence.models import PresenceCheck
from voteit.presence.permissions import PresenceCheckPermissions
from voteit.presence.permissions import PresencePermissions

User: AbstractUser = get_user_model()


class AddPresenceSchema(BaseModel):
    presence_check: int  # The context for add


class PresenceSchema(BaseModel):
    pk: int


@incoming
class AddPresence(BaseAddObject):
    name = "presence.add"
    schema = AddPresenceSchema
    data: AddPresenceSchema
    permission = PresencePermissions.ADD
    model = PresenceCheck
    add_model = Presence
    relation_queryset_attribute = "presences"
    context_pk_attr = "presence_check"
    context: PresenceCheck

    def run_job(self) -> StatusDone:
        self.assert_perm(msg=_("You're not allowed to set yourself as present here."))
        self.context.presences.get_or_create(user=self.user)
        if self.mm.consumer_name is not None:
            response = StatusDone.from_message(self)
            response.send_outgoing(self.mm.consumer_name, success=True)
            return response


@incoming
class DeletePresence(BaseDeleteObject):
    name = "presence.delete"
    schema = PresenceSchema
    data: PresenceSchema
    permission = PresencePermissions.DELETE
    model = Presence

    def run_job(self) -> StatusDone:
        self.assert_perm(msg=_("You're not allowed to remove yourself."))
        self.context.delete()
        if self.mm.consumer_name is not None:
            response = StatusDone.from_message(self)
            response.send_outgoing(self.mm.consumer_name, success=True)
            return response


class AddUserPresenceSchema(AddPresenceSchema):
    userid: int


class UserPresenceSchema(PresenceSchema):
    userid: int


@incoming
class AddUserPresence(BaseAddObject):
    name = "presence.add_user"
    schema = AddUserPresenceSchema
    data: AddUserPresenceSchema
    permission = PresenceCheckPermissions.CHANGE
    model = PresenceCheck
    add_model = Presence
    relation_queryset_attribute = "presences"
    context_pk_attr = "presence_check"
    context: PresenceCheck

    def run_job(self) -> StatusDone:
        self.assert_perm(msg=_("You're not allowed to change presence check."))
        user = User.objects.filter(pk=self.data.userid).first()
        if user is None:
            raise ValidationErrorMsg.from_message(
                self,
                msg=_("User doesn't exist"),
                errors=[{"loc": ("userid",), "msg": "Invalid", "type": "value.error"}],
            )
        if user.has_perm(PresencePermissions.ADD, self.context):
            self.context.presences.create(user=user)
            if self.mm.consumer_name is not None:
                response = StatusDone.from_message(self)
                response.send_outgoing(self.mm.consumer_name, success=True)
                return response  # For testing
        else:
            raise ValidationErrorMsg.from_message(
                self,
                msg=_(
                    "User can't be present here. Perhaps that user isn't a participant?"
                ),
                errors=[{"loc": ("userid",), "msg": "Invalid", "type": "value.error"}],
            )


@incoming
class DeleteUserPresence(BaseDeleteObject):
    name = "presence.delete_user"
    permission = PresencePermissions.DELETE
    model = Presence
    schema = PresenceSchema
    data: PresenceSchema

    def run_job(self) -> StatusDone:
        self.assert_perm(msg=_("You're not allowed to delete presence."))
        self.context.delete()
        if self.mm.consumer_name is not None:
            response = StatusDone.from_message(self)
            response.send_outgoing(self.mm.consumer_name, success=True)
            return response  # For testing


@outgoing
class PresenceCheckAdded(BaseObjectAdded):
    name = "presence_check.added"


@outgoing
class PresenceCheckChanged(BaseObjectChanged):
    name = "presence_check.changed"


@outgoing
class PresenceCheckDeleted(BaseObjectDeleted):
    name = "presence_check.deleted"


class PresenceCheckStatusSchema(BaseModel):
    pk: int
    present: int


@outgoing
class PresenceCheckStatus(BaseOutgoingMessage):
    name = "presence_check.status"
    schema = PresenceCheckStatusSchema
    data: PresenceCheckStatusSchema


@outgoing
class PresenceAdded(BaseObjectAdded):
    name = "presence.added"


@outgoing
class PresenceDeleted(BaseObjectDeleted):
    name = "presence.deleted"
