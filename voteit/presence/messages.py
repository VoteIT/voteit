from django.contrib.auth import get_user_model
from pydantic.main import BaseModel
from django.utils.translation import gettext as _

from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.decorators import outgoing
from voteit.messaging.decorators import incoming
from voteit.messaging.errors import ValidationErrorMsg
from voteit.messaging.messages.base import (
    BaseAddObject,
    BaseDeleteObject,
    BaseObjectChanged,
    BaseObjectAdded,
    BaseObjectDeleted,
)
from voteit.messaging.messages.text import TextResponse
from voteit.presence.models import Presence
from voteit.presence.models import PresenceCheck
from voteit.presence.permissions import PresenceCheckPermissions
from voteit.presence.permissions import PresencePermissions


User = get_user_model()


class PresenceSchema(BaseModel):
    pk: int  # presence check object for add, presence for other operations


@incoming
class AddPresence(BaseAddObject):
    name = "presence.add"
    schema = PresenceSchema
    data: PresenceSchema
    permission = PresencePermissions.ADD
    model = PresenceCheck
    add_model = Presence

    def run_job(self):
        self.assert_perm(msg=_("You're not allowed to set yourself as present here."))
        self.add_model.objects.create(user=self.user, presence_check=self.context)
        if self.mm.consumer_name is not None:
            response = TextResponse.from_message(self, msg="Added")
            response.send_outgoing(self.mm.consumer_name, success=True)
            return response


@incoming
class DeletePresence(BaseDeleteObject):
    name = "presence.delete"
    schema = PresenceSchema
    data: PresenceSchema
    permission = PresencePermissions.DELETE
    model = Presence

    def run_job(self):
        self.assert_perm(msg=_("You're not allowed to remove yourself."))
        self.context.delete()
        if self.mm.consumer_name is not None:
            response = TextResponse.from_message(self, msg="Removed")
            response.send_outgoing(self.mm.consumer_name, success=True)


class UserPresenceSchema(PresenceSchema):
    userid: int


@incoming
class AddUserPresence(BaseAddObject):
    name = "presence.add_user"
    schema = UserPresenceSchema
    data: UserPresenceSchema
    permission = PresenceCheckPermissions.CHANGE
    model = PresenceCheck
    add_model = Presence

    def run_job(self):
        self.assert_perm(msg=_("You're not allowed to change presence check."))
        user = User.objects.filter(pk=self.data.userid).first()
        if user is None:
            raise ValidationErrorMsg.from_message(
                self,
                msg=_("User doesn't exist"),
                errors=[{"loc": ("userid",), "msg": "Invalid", "type": "value.error"}],
            )
        if user.has_perm(PresencePermissions.ADD, self.context):
            self.add_model.objects.create(user=user, presence_check=self.context)
            if self.mm.consumer_name is not None:
                response = TextResponse.from_message(self, msg="Added")
                response.send_outgoing(self.mm.consumer_name, success=True)
                return response  # For testing
        else:
            raise ValidationErrorMsg.from_message(
                self,
                msg=_("User can't be present here. Perhaps that user isn't a participant?"),
                errors=[{"loc": ("userid",), "msg": "Invalid", "type": "value.error"}],
            )


@incoming
class DeleteUserPresence(BaseDeleteObject):
    name = "presence.delete_user"
    permission = PresencePermissions.DELETE
    model = Presence
    schema = PresenceSchema
    data: PresenceSchema

    def run_job(self):
        self.assert_perm(msg=_("You're not allowed to delete presence."))
        self.context.delete()
        if self.mm.consumer_name is not None:
            response = TextResponse.from_message(self, msg="Deleted")
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
class PresenceChanged(BaseObjectChanged):
    name = "presence.changed"


@outgoing
class PresenceDeleted(BaseObjectDeleted):
    name = "presence.deleted"
