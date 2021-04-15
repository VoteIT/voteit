from __future__ import annotations

from typing import List
from typing import Optional
from typing import Tuple
from typing import Type

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from pydantic import BaseModel
from pydantic import Field
from pydantic import root_validator
from pydantic import validator
from voteit.core.models import RoleContextMixin
from voteit.core.permissions import NOT_ALLOWED
from voteit.core.schemas import RoleOutput
from voteit.core.utils import get_model_by_shortname
from voteit.core.utils import get_model_shortname
from voteit.core.utils import get_permission_registry
from voteit.core.validators import root_validate_roles_and_model
from voteit.core.validators import validate_roles_context_model
from voteit.messaging.abcs import AsyncRunnable
from voteit.messaging.abcs import BaseIncomingMessage
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.abcs import ContextAction
from voteit.messaging.abcs import DeferredJob
from voteit.messaging.channels.user import UserChannel
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing
from voteit.messaging.errors import ValidationErrorMsg
from voteit.messaging.messages.channels import RecheckChannelSubscriptions
from voteit.messaging.messages.text import TextResponse

User = get_user_model()


class ChangeRolesSchema(BaseModel):
    """
    Typical valid input:
    >>> ChangeRolesSchema(userids=[1], roles=["participant"], model="meeting", pk=2)
    ChangeRolesSchema(pk=2, userids=[1], roles=['participant'], model='meeting')

    Valid role but not for this context:
    >>> ChangeRolesSchema(userids=[1], roles=["speaker"], model="meeting", pk=2)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError:
    """

    pk: int
    userids: List[int]
    roles: List[str]  # We have no clue of roles are valid here
    model: str  # The short name of the model to change roles in

    # Validators
    _validate_model = validator("model", allow_reuse=True)(validate_roles_context_model)
    _check_roles = root_validator(skip_on_failure=True, allow_reuse=True)(
        root_validate_roles_and_model
    )


class BaseRoles(BaseIncomingMessage, DeferredJob, ContextAction):
    schema = ChangeRolesSchema
    data: ChangeRolesSchema
    context_pk_attr = "pk"

    @property
    def model(self) -> Type[RoleContextMixin]:
        return get_model_by_shortname(self.data.model)

    @cached_property
    def permission(self) -> str:
        model_name = get_model_shortname(self.context)
        reg = get_permission_registry()
        model_perms = reg.get_model_permissions(model_name)
        return getattr(model_perms, "CHANGE_ROLES", NOT_ALLOWED)

    def validate_and_fetch(self) -> models.QuerySet:
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


@incoming
class AddRoles(BaseRoles):
    name = "roles.add"
    schema = ChangeRolesSchema
    data: ChangeRolesSchema

    def run_job(self):
        users_qs = self.validate_and_fetch()
        for user in users_qs:
            self.context.add_roles(user, *self.data.roles)
        if self.mm.consumer_name:  # If this is a script, consumer_name will be None
            response = TextResponse.from_message(self, msg="Added")
            response.send_outgoing(self.mm.consumer_name, success=True)


@incoming
class RemoveRoles(BaseRoles):
    name = "roles.remove"
    schema = ChangeRolesSchema
    data: ChangeRolesSchema

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


class GetRolesSchema(BaseModel):
    pk: int = Field(title="pk of context")
    model: str = Field(title="Model name, lowercased, like 'agenda_item'")
    filter_userids: Optional[List[int]] = Field(
        title="If set: Only check these userids"
    )
    _validate_model = validator("model", allow_reuse=True)(validate_roles_context_model)


@incoming
class GetRoles(BaseIncomingMessage, DeferredJob, ContextAction):
    """ Transmits a dict looking like AssignedResponseSchema with user_pk and assigned roles. """

    name = "roles.get"
    schema = GetRolesSchema
    data: GetRolesSchema
    context_pk_attr = "pk"

    @cached_property
    def permission(self) -> str:
        model_name = get_model_shortname(self.context)
        reg = get_permission_registry()
        model_perms = reg.get_model_permissions(model_name)
        return getattr(model_perms, "VIEW_ROLES", NOT_ALLOWED)

    @property
    def model(self) -> Type[RoleContextMixin]:
        return get_model_by_shortname(self.data.model)

    def run_job(self) -> AssignedRolesResponse:
        self.assert_perm()
        kwargs = dict(context=self.context)
        if self.data.filter_userids:
            kwargs["user__in"] = self.data.userids
        qs = self.context.roles_cls.objects.filter(**kwargs).values(
            "user_id", "assigned"
        )
        items = [(item["user_id"], item["assigned"]) for item in qs]
        msg = AssignedRolesResponse.from_message(self, items=items)
        msg.send_outgoing(self.mm.consumer_name, success=True)
        return msg


class AssignedResponseSchema(BaseModel):
    """Return a dict with assigned roles where key is user_pk and value is a list of roles as strings"""

    items: List[Tuple[int, List[str]]] = Field(
        title="Assigned roles",
        description="Key is user_pk and value the assigned roles.",
    )


@outgoing
class AssignedRolesResponse(BaseOutgoingMessage):
    name = "roles.assigned"
    schema = AssignedResponseSchema
    data: AssignedResponseSchema


class AvailableRolesSchema(BaseModel):
    model: str = Field(title="Model name, lowercased, like 'agenda_item'")
    predicates: bool = False
    _validate_model = validator("model", allow_reuse=True)(validate_roles_context_model)


@incoming
class AvailableRoles(BaseIncomingMessage, AsyncRunnable):
    name = "roles.available"
    schema = AvailableRolesSchema
    data: AvailableRolesSchema

    async def run(self, consumer):
        model = get_model_by_shortname(self.data.model)
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
