from typing import Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext as _
from pydantic import validator
from pydantic.main import BaseModel
from envelope.core.message import Message
from envelope.messages.common import Status
from envelope.messages.errors import UnauthorizedError
from envelope.messages.errors import ValidationErrorMsg
from envelope.utils import websocket_send

from voteit.messaging.base import AddedOrUpdatedSchema
from voteit.messaging.base import BaseObjectAction
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.presence.models import PresenceCheck
from voteit.presence.permissions import PresenceCheckPermissions
from voteit.presence.permissions import PresencePermissions


class ChangePresenceSchema(BaseModel):
    presence_check: int
    present: bool
    # Moderators can specify other users
    user: Optional[int]

    @validator("user", pre=True)
    def cast_user(cls, v):
        if isinstance(v, AbstractUser):
            v = v.pk
        return v


@incoming
class ChangePresence(BaseObjectAction):
    name = "presence.change"
    schema = ChangePresenceSchema
    data: ChangePresenceSchema
    permission = PresencePermissions.CHANGE
    model = PresenceCheck
    context_schema_attr = "presence_check"
    context: PresenceCheck

    def run_job(self) -> Status:
        if self.data.user is None:
            # Someone is adding themselves
            self.assert_perm()
            user_to_modify = self.user
        else:
            # A moderator is adding someone
            User: AbstractUser = get_user_model()
            user_to_modify = User.objects.filter(pk=self.data.user).first()
            if user_to_modify is None:
                raise ValidationErrorMsg.from_message(
                    self,
                    msg=_("User doesn't exist"),
                    errors=[
                        {"loc": ("user",), "msg": "Invalid", "type": "value.error"}
                    ],
                )
            # The posting user must have permission to modify the presence check itself to be able to add other users
            if not self.user.has_perm(PresenceCheckPermissions.CHANGE, self.context):
                raise UnauthorizedError.from_message(
                    self,
                    permission=PresenceCheckPermissions.CHANGE,
                    model=PresenceCheck,
                    value=self.context.pk,
                )
            # And if the user the moderator wants to change can't do that operation themselves,
            # it's a validation error for the moderator but only on add. We'll let moderators remove users who
            # can't enter the list themselves for some reason. (For instance removed permissions)
            if self.data.present and not user_to_modify.has_perm(
                PresencePermissions.CHANGE, self.context
            ):
                raise ValidationErrorMsg.from_message(
                    self,
                    msg=_(
                        "User can't be present here - maybe they're not a participant?"
                    ),
                    errors=[
                        {"loc": ("user",), "msg": "Invalid", "type": "value.error"}
                    ],
                )
        # Modifications will be pushed to presence check channel + to specific user. See signals
        if self.data.present:
            self.context.presences.get_or_create(user=user_to_modify)
        else:
            presence = self.context.presences.filter(user=user_to_modify).first()
            if presence is not None:
                presence.delete()
        if self.mm.consumer_name is not None:
            response = Status.from_message(self)
            websocket_send(response, state=response.SUCCESS)
            return response


@outgoing
class PresenceCheckAdded(BaseObjectAdded):
    name = "presence_check.added"
    schema = AddedOrUpdatedSchema
    data: AddedOrUpdatedSchema


@outgoing
class PresenceCheckChanged(BaseObjectChanged):
    name = "presence_check.changed"
    schema = AddedOrUpdatedSchema
    data: AddedOrUpdatedSchema


@outgoing
class PresenceCheckDeleted(BaseObjectDeleted):
    name = "presence_check.deleted"


class PresenceChangedSchema(AddedOrUpdatedSchema):
    user: int
    presence_check: int


@outgoing
class PresenceAdded(Message):
    name = "presence.added"
    schema = PresenceChangedSchema
    data: PresenceChangedSchema


@outgoing
class PresenceDeleted(Message):
    name = "presence.deleted"
    schema = PresenceChangedSchema
    data: PresenceChangedSchema
