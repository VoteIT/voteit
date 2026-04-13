from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

from auditlog.context import set_actor
from django.contrib.auth import get_user_model
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from pydantic import Field
from pydantic import root_validator
from pydantic import validator
from pydantic.main import BaseModel
from envelope import INTERNAL
from envelope.channels.messages import RecheckChannelSubscriptions
from envelope.core.message import AsyncRunnable
from envelope.core.message import Message
from envelope.deferred_jobs.message import ContextAction
from envelope.messages.common import Status
from envelope.messages.errors import ValidationErrorMsg
from envelope.utils import websocket_send

from voteit.core import PERM
from voteit.core.loggers import log_roles_change
from voteit.core.role import Role
from voteit.core.schemas import RoleOutput
from voteit.core.utils import get_model_by_shortname
from voteit.core.validators import root_validate_roles_and_model
from voteit.core.validators import validate_roles_context_model
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing

if TYPE_CHECKING:
    from voteit.core.models import RoleContextMixin


class ChangeRolesSchema(BaseModel):
    """
    Typical valid input:
    >>> from voteit.meeting.roles import ROLE_PARTICIPANT
    >>> ChangeRolesSchema(users=[1], roles=[ROLE_PARTICIPANT], model="meeting", pk=2)
    ChangeRolesSchema(pk=2, users=[1], roles=['pa'], model='meeting')

    Valid role but not for this context:
    >>> from voteit.speaker.roles import ROLE_SPEAKER
    >>> ChangeRolesSchema(users=[1], roles=[ROLE_SPEAKER], model="meeting", pk=2)
    Traceback (most recent call last):
    ...
    pydantic.error_wrappers.ValidationError:
    """

    pk: int
    users: list[int]
    roles: list[str]
    model: str  # The short name of the model to change roles in

    # Validators
    _validate_model = validator("model", allow_reuse=True)(validate_roles_context_model)
    _check_roles = root_validator(skip_on_failure=True, allow_reuse=True)(
        root_validate_roles_and_model
    )

    @validator("roles", pre=True, each_item=True)
    def roles_to_str(cls, v: str | Role):
        if isinstance(v, Role):
            v = str(v)
        return v


class BaseRoles(ContextAction, ABC):
    schema = ChangeRolesSchema
    data: ChangeRolesSchema

    @property
    def model(self) -> type[RoleContextMixin]:
        return get_model_by_shortname(self.data.model)

    @cached_property
    def permission(self) -> str:
        return self.context.get_perm(PERM.CHANGE_ROLES)

    def validate_and_fetch(self) -> models.QuerySet:
        # Permission
        self.assert_perm()
        # Users
        User = get_user_model()
        users_qs = User.objects.filter(pk__in=self.data.users)
        if len(self.data.users) != users_qs.count():
            raise ValidationErrorMsg.from_message(
                self,
                msg=_("Some users don't exist, aborting"),
                errors=[{"loc": ("users",), "msg": "Invalid", "type": "value.error"}],
            )
        return users_qs


@incoming
class AddRoles(BaseRoles):
    name = "roles.add"
    schema = ChangeRolesSchema
    data: ChangeRolesSchema

    def run_job(self) -> Status:
        users_qs = self.validate_and_fetch()
        with set_actor(self.user):
            for user in users_qs:
                if roles_objs := self.context.add_roles(user, *self.data.roles):
                    log_roles_change(
                        "Added",
                        actor=self.user,
                        for_user=user,
                        context=self.context,
                        roles=roles_objs,
                    )
        if self.mm.consumer_name:  # If this is a script, consumer_name will be None
            response = Status.from_message(self)
            websocket_send(response, state=response.SUCCESS)
            return response


@incoming
class RemoveRoles(BaseRoles):
    name = "roles.remove"
    schema = ChangeRolesSchema
    data: ChangeRolesSchema

    def run_job(self) -> Status:
        # Avoid problems without user model
        from envelope.app.user_channel.channel import UserChannel

        users_qs = self.validate_and_fetch()
        notify_users = set()
        with set_actor(self.user):
            for user in users_qs:
                if roles_objs := self.context.remove_roles(user, *self.data.roles):
                    log_roles_change(
                        "Removed",
                        actor=self.user,
                        for_user=user,
                        context=self.context,
                        roles=roles_objs,
                    )
                    notify_users.add(user)
        response = None
        if self.mm.consumer_name:  # If this is a script, consumer_name will be None
            response = Status.from_message(self)
            websocket_send(response, state=response.SUCCESS)
        # FIXME: Why these defaults?
        msg = RecheckChannelSubscriptions(consumer_name="", subscriptions=[])
        for user in notify_users:
            user_channel = UserChannel.from_instance(user, envelope_name=INTERNAL)
            user_channel.sync_publish(msg)
        if response:
            return response


class GetRolesSchema(BaseModel):
    pk: int = Field(title="pk of context")
    model: str = Field(title="Model name, lowercased, like 'agenda_item'")
    filter_users: list[int] | None = Field(title="If set: Only check these users")
    _validate_model = validator("model", allow_reuse=True)(validate_roles_context_model)


@incoming
class GetRoles(ContextAction):
    """Transmits a dict looking like AssignedResponseSchema with user_pk and assigned roles."""

    name = "roles.get"
    schema = GetRolesSchema
    data: GetRolesSchema

    @cached_property
    def permission(self) -> str:
        return self.context.get_perm(PERM.CHANGE_ROLES)

    @property
    def model(self) -> type[RoleContextMixin]:
        return get_model_by_shortname(self.data.model)

    def run_job(self) -> AssignedRolesResponse:
        self.assert_perm()
        kwargs = dict(context=self.context)
        if self.data.filter_users:
            kwargs["user__in"] = self.data.users
        qs = self.context.roles_cls.objects.filter(**kwargs).values(
            "user_id", "assigned"
        )
        items = [(item["user_id"], item["assigned"]) for item in qs]
        msg = AssignedRolesResponse.from_message(self, items=items)
        websocket_send(msg, state=msg.SUCCESS, on_commit=False)
        return msg


class AssignedResponseSchema(BaseModel):
    """Return a dict with assigned roles where key is user_pk and value is a list of roles as strings"""

    items: list[tuple[int, list[str]]] = Field(
        title="Assigned roles",
        description="Key is user_pk and value the assigned roles.",
    )


@outgoing
class AssignedRolesResponse(Message):
    name = "roles.assigned"
    schema = AssignedResponseSchema
    data: AssignedResponseSchema


class AvailableRolesSchema(BaseModel):
    model: str = Field(title="Model name, lowercased, like 'agenda_item'")
    predicates: bool = False
    _validate_model = validator("model", allow_reuse=True)(validate_roles_context_model)


@incoming
class AvailableRoles(AsyncRunnable):
    name = "roles.available"
    schema = AvailableRolesSchema
    data: AvailableRolesSchema

    async def run(self, *, consumer, **kwargs):
        model = get_model_by_shortname(self.data.model)
        roles = [x.output() for x in model.roles_cls.valid_roles.values()]
        if not self.data.predicates:
            for role in roles:
                # We don't need to send this
                role.predicate_info = None
        response = AvailableRolesResponse.from_message(
            self, roles=roles, state=AvailableRoles.SUCCESS
        )
        await consumer.send_ws_message(response)
        return response


class AvailableRolesResponseSchema(BaseModel):
    roles: list[RoleOutput]


@outgoing
class AvailableRolesResponse(Message):
    name = "roles.available"
    schema = AvailableRolesResponseSchema
    data: AvailableRolesResponseSchema
