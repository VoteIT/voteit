from __future__ import annotations

from abc import abstractmethod, ABC
from typing import List, Type, Optional, Set, Dict

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext as _
from pydantic import BaseModel

from voteit.core.models import RoleContextMixin
from voteit.core.schemas import RoleOutput
from voteit.meeting.models import Meeting, MeetingRoles
from voteit.meeting.permissions import MeetingPermissions
from voteit.messaging.abcs import (
    BaseIncomingMessage,
    DeferredJob,
    ContextAction,
    ContextSchema,
    BaseOutgoingMessage,
)
from voteit.messaging.decorators import incoming, outgoing
from voteit.messaging.errors import UnauthorizedError
from voteit.messaging.errors import ValidationErrorMsg
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
        response = TextResponse.from_message(self, msg="Added")
        response.send_outgoing(self.mm.consumer_name, success=True)


class BaseRemoveRoles(BaseRoles, ABC):
    def run_job(self):
        users_qs = self.validate_and_fetch()
        for user in users_qs:
            self.context.remove_roles(user, *self.data.roles)
        response = TextResponse.from_message(self, msg="Removed")
        response.send_outgoing(self.mm.consumer_name, success=True)


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
    pk: int  # The meeting we want to know about
    filter_userids: Optional[List[int]]


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
    """ Return a dict with assigned roles where key is user_pk and value is a list of roles as strings
    """
    items: Dict[int, List[str]]


@outgoing
class AssignedMeetingRolesResponse(BaseOutgoingMessage):
    name = "meeting.roles.assigned"
    schema = AssignedResponseSchema
    data: AssignedResponseSchema


class BaseAvailableRoles(BaseIncomingMessage, DeferredJob, ContextAction, ABC):
    def run_job(self) -> AvailableRolesResponse:
        assert isinstance(self.context, RoleContextMixin)
        roles = [x.output() for x in self.context.roles_cls.valid_roles.values()]
        response = AvailableRolesResponse.from_message(self, roles=roles)
        response.send_outgoing(self.mm.consumer_name, success=True)
        return response

@incoming
class AvailableMeetingRoles(BaseAvailableRoles):
    name = "meeting.roles.available"
    model = Meeting
    permission = None


class AvailableRolesSchema(BaseModel):
    roles: List[RoleOutput]


@outgoing
class AvailableRolesResponse(BaseOutgoingMessage):
    name = "roles.available"
    schema = AvailableRolesSchema
    data: AvailableRolesSchema
