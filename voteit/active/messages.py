from auditlog.context import set_actor
from django.contrib.auth import get_user_model
from pydantic import BaseModel
from pydantic import conint
from pydantic import validator

from envelope.deferred_jobs.message import ContextAction
from envelope.core.message import Message
from envelope.messages.common import Status
from envelope.messages.errors import BadRequestError
from envelope.messages.errors import UnauthorizedError
from envelope.utils import websocket_send

from voteit.active.models import ActiveUser
from voteit.active.utils import get_inactive_qs
from voteit.core import PERM
from voteit.meeting.models import Meeting
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing


class SetActiveSchema(BaseModel):
    meeting: conint(ge=1)
    user: int | None
    active: bool

    @validator("user", pre=True)
    def transform_user(cls, v):
        if v and not isinstance(v, int):
            User = get_user_model()
            if isinstance(v, User):
                return v.pk
        return v


@incoming
class SetActive(ContextAction):
    name = "active_user.set"
    schema = SetActiveSchema
    data: SetActiveSchema
    permission = ActiveUser.get_perm(PERM.CHANGE)
    model = Meeting
    context_schema_attr = "meeting"

    def run_job(self):
        self.assert_perm()
        meeting: Meeting = self.context
        if self.data.user:
            if self.data.user != self.user.pk and not self.user.has_perm(
                Meeting.get_perm(PERM.MODERATE), self.context
            ):
                # if set and user isn't moderator
                raise UnauthorizedError.from_message(
                    self,
                    model=self.model,
                    key=self.context_query_kw,
                    value=getattr(self.data, self.context_schema_attr),
                    permission=self.permission,
                )
            # Check that user's part of the meeting
            if not meeting.participants.filter(pk=self.data.user).exists():
                raise BadRequestError.from_message(self, msg="User not part of meeting")
        else:
            self.data.user = self.user.pk
        with set_actor(self.user):
            if self.data.active:
                meeting.active_users.update_or_create(user_id=self.data.user)
            else:
                meeting.active_users.filter(user_id=self.data.user).delete()
        response = Status.from_message(self)
        websocket_send(response, state=self.SUCCESS)
        return response


class ActiveUserChangedSchema(BaseModel):
    meeting: int
    user: int
    active: bool


@outgoing
class ActiveUserChanged(Message):
    name = "active_user.changed"
    schema = ActiveUserChangedSchema
    data: ActiveUserChangedSchema


class ActiveUsersSchema(BaseModel):
    meeting: int
    users: list[int]


@outgoing
class ActiveUsers(Message):
    name = "active_user.all"
    schema = ActiveUsersSchema
    data: ActiveUsersSchema


class PurgeInactiveUsersSchema(BaseModel):
    meeting: conint(ge=1)
    hours: conint(ge=0) = 1


@incoming
class PurgeInactiveUsers(ContextAction):
    name = "active_user.purge"
    schema = PurgeInactiveUsersSchema
    data: PurgeInactiveUsersSchema
    permission = Meeting.get_perm(PERM.CHANGE)
    model = Meeting
    context_schema_attr = "meeting"

    def run_job(self):
        self.assert_perm()
        older_active_users = get_inactive_qs(self.context, hours=self.data.hours)
        response = PurgeInactiveResponse.from_message(
            self, count=older_active_users.count()
        )
        older_active_users.delete()
        websocket_send(response, state=self.SUCCESS)
        return response


class PurgeInactiveResponseSchema(BaseModel):
    count: int


@outgoing
class PurgeInactiveResponse(Message):
    name = "active_user.purge"
    schema = PurgeInactiveResponseSchema
    data: PurgeInactiveResponseSchema
