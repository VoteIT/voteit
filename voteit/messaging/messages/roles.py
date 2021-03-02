from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import Dict
from typing import List
from typing import Optional
from typing import Type

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext as _
from pydantic import BaseModel
from pydantic import Field
from pydantic import validator

from voteit.core.models import RoleContextMixin
from voteit.core.schemas import RoleOutput
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles
from voteit.meeting.permissions import MeetingPermissions
from voteit.messaging.abcs import AsyncRunnable
from voteit.messaging.abcs import BaseIncomingMessage
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.abcs import ContextAction
from voteit.messaging.abcs import ContextSchema
from voteit.messaging.abcs import DeferredJob
from voteit.messaging.channels.user import UserChannel
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.messaging.errors import ValidationErrorMsg
from voteit.messaging.messages.channels import RecheckChannelSubscriptions
from voteit.messaging.messages.text import TextResponse

User = get_user_model()


class ChangeRolesSchema(ContextSchema):
    userids: List[int]
    roles: List[str]
    # We have no clue of roles are valid here


class BaseRoles(BaseIncomingMessage, DeferredJob, ContextAction):
    schema = ChangeRolesSchema
    data: ChangeRolesSchema

    @property
    @abstractmethod
    def model(self) -> Type[RoleContextMixin]:
        pass

    def validate_and_fetch(self) -> models.QuerySet:
        # Roles
        assert isinstance(self.context, RoleContextMixin)
        invalid = set(self.data.roles) - self.context.filter_valid_roles(
            *self.data.roles
        )
        if invalid:
            raise ValidationErrorMsg.from_message(
                self,
                msg=_("Invalid roles"),
                errors=[
                    {
                        "loc": ("roles",),
                        "msg": _("Invalid: %(roles)s" % {"roles": invalid}),
                        "type": "value.error",
                    }
                ],
            )
        # Permission
        self.assert_perm(msg=_("You're not allowed to change roles"))
        # Users
        users_qs = User.objects.filter(pk__in=self.data.userids)
        if len(self.data.userids) != users_qs.count():
            raise ValidationErrorMsg.from_message(
                self,
                msg=_("Some users don't exist, aborting"),
                errors=[{"loc": ("userids",), "msg": "Invalid", "type": "value.error"}],
            )
        return users_qs


class BaseAddRoles(BaseRoles, ABC):
    def run_job(self):
        users_qs = self.validate_and_fetch()
        for user in users_qs:
            self.context.add_roles(user, *self.data.roles)
        if self.mm.consumer_name:  # If this is a script, consumer_name will be None
            response = TextResponse.from_message(self, msg="Added")
            response.send_outgoing(self.mm.consumer_name, success=True)


class BaseRemoveRoles(BaseRoles, ABC):
    def run_job(self):
        users_qs = self.validate_and_fetch()
        notify_users = set()
        for user in users_qs:
            if self.context.remove_roles(user, *self.data.roles):
                notify_users.add(user)
        if self.mm.consumer_name:  # If this is a script, consumer_name will be None
            response = TextResponse.from_message(self, msg="Removed")
            response.send_outgoing(self.mm.consumer_name, success=True)
        msg = RecheckChannelSubscriptions()
        for user in notify_users:
            user_channel = UserChannel.from_instance(user)
            user_channel.publish(msg, internal=True)


@incoming
class AddMeetingRoles(BaseAddRoles):
    name = "meeting.roles.add"
    model = Meeting
    permission = MeetingPermissions.CHANGE


@incoming
class RemoveMeetingRoles(BaseRemoveRoles):
    name = "meeting.roles.remove"
    model = Meeting
    permission = MeetingPermissions.CHANGE


class GetMeetingRolesSchema(BaseModel):
    pk: int = Field(title="Meeting pk")
    filter_userids: Optional[List[int]] = Field(
        title="If set: Only check these userids"
    )


@incoming
class GetMeetingRoles(BaseIncomingMessage, DeferredJob, ContextAction):
    """ Transmits a dict looking like AssignedResponseSchema with user_pk and assigned roles. """

    name = "meeting.roles.get"
    model = Meeting
    permission = MeetingPermissions.VIEW
    schema = GetMeetingRolesSchema
    data: GetMeetingRolesSchema

    def run_job(self) -> AssignedMeetingRolesResponse:
        self.assert_perm()
        kwargs = dict(context=self.context)
        if self.data.filter_userids:
            kwargs["user__in"] = self.data.userids
        qs = MeetingRoles.objects.filter(**kwargs).values("user_id", "assigned")
        items = {}
        for item in qs:
            items[item["user_id"]] = item["assigned"]
        msg = AssignedMeetingRolesResponse.from_message(self, items=items)
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


class AssignedResponseSchema(BaseModel):
    """Return a dict with assigned roles where key is user_pk and value is a list of roles as strings"""

    items: Dict[int, List[str]] = Field(
        title="Assigned roles",
        description="Key is user_pk and value the assigned roles.",
    )


@outgoing
class AssignedMeetingRolesResponse(BaseOutgoingMessage):
    name = "meeting.roles.assigned"
    schema = AssignedResponseSchema
    data: AssignedResponseSchema


class AvailableRolesSchema(BaseModel):
    natural_key: str
    predicates: bool = False

    @validator("natural_key")
    def check_natural_key(cls, v):
        v = v.lower()
        parts = v.split(".")
        if len(parts) != 2:
            raise ValueError("Model key must contain one dot")
        try:
            model = apps.get_model(*parts)
        except LookupError:
            raise ValueError(f"No model found with natural key {v}")
        if not issubclass(model, RoleContextMixin):
            raise ValueError(f"Model {v} can't have roles")
        return v


@incoming
class AvailableRoles(BaseIncomingMessage, AsyncRunnable):
    name = "roles.available"
    schema = AvailableRolesSchema
    data: AvailableRolesSchema

    async def run(self, consumer):
        key_parts = self.data.natural_key.split(".")
        model = apps.get_model(*key_parts)
        roles = [x.output() for x in model.roles_cls.valid_roles.values()]
        if not self.data.predicates:
            for role in roles:
                # We don't need to send this
                role.predicate_info = None
        response = AvailableRolesResponse.from_message(self, roles=roles)
        await response.async_send_outgoing(self.mm.consumer_name, success=True)
        return response


class AvailableRolesResponseSchema(BaseModel):
    roles: List[RoleOutput]


@outgoing
class AvailableRolesResponse(BaseOutgoingMessage):
    name = "roles.available"
    schema = AvailableRolesResponseSchema
    data: AvailableRolesResponseSchema
