from auditlog.context import set_actor
from django.contrib.auth import get_user_model
from pydantic import BaseModel
from pydantic import validator

from envelope.core.message import ContextAction
from envelope.core.message import Message
from envelope.messages.common import Status
from envelope.messages.errors import BadRequestError
from envelope.messages.errors import UnauthorizedError
from envelope.utils import websocket_send

from voteit.active.permissions import ActiveUserPermissions
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.messaging.base import AddedOrUpdatedSchema
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing


class SetActiveSchema(BaseModel):
    meeting: int
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
    permission = ActiveUserPermissions.CHANGE
    model = Meeting
    context_schema_attr = "meeting"

    def run_job(self):
        self.assert_perm()
        meeting: Meeting = self.context
        if self.data.user:
            if self.data.user != self.user.pk and not self.user.has_perm(
                MeetingPermissions.MODERATE, self.context
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
        existing = meeting.active_users.filter(user_id=self.data.user).first()
        with set_actor(self.user):
            if self.data.active:
                # Set active
                if not existing:
                    meeting.active_users.create(user_id=self.data.user)
                else:
                    raise BadRequestError.from_message(self, msg="User already active")
            else:
                # Remove active
                if existing is not None:
                    existing.delete()
                else:
                    raise BadRequestError.from_message(self, msg="User isn't active")
        response = Status.from_message(self)
        websocket_send(response, state=self.SUCCESS)
        return response


class ActiveUserChangedSchema(BaseModel):
    user: int
    active: bool


@outgoing
class ActiveUserChanged(Message):
    name = "active_user.changed"
    schema = ActiveUserChangedSchema
    data: ActiveUserChangedSchema


class ActiveUsersSchema(BaseModel):
    users: list[int]


@outgoing
class ActiveUsers(Message):
    name = "active_user.all"
    schema = ActiveUsersSchema
    data: ActiveUsersSchema
