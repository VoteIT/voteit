from __future__ import annotations

from typing import List, TYPE_CHECKING

from django.contrib.auth import get_user_model
from pydantic import validator
from django.utils.translation import gettext as _

from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.messaging.messages.abcs import AbstractIncomingMessage
from voteit.messaging.registries import websocket_incoming_messages
from voteit.messaging.jobs import change_roles

if TYPE_CHECKING:
    from voteit.messaging.consumers import WebsocketDemuxConsumer


User = get_user_model()


class AbstractChangeRoles(AbstractIncomingMessage):
    userids: List[int]  # Validation deferred to job
    roles: List[str]
    pk: int  # context pk, meeting for instance

    class Config:
        model = None
        action = None
        permission = "__NEVER"

    @validator("roles")
    def validate_roles(cls, v: List[str]):
        valid = cls.Config.model.roles_cls.valid_roles
        for role in v:
            if role not in valid:
                raise ValueError(f"{role} is not a valid role for {cls.Config.model}")
        return v

    async def consume(self, consumer: WebsocketDemuxConsumer, message_id: str = None):
        change_roles.delay(
            message_id=message_id,
            consumer_name=consumer.channel_name,
            user_pk=consumer.user.pk,
            action=self.Config.action,
            permission=self.Config.permission,
            model=self.Config.model,
            **self.dict(),
        )


@websocket_incoming_messages("meeting.roles.add")
class AddMeetingRoles(AbstractChangeRoles):
    class Config:
        model = Meeting
        action = "add"
        permission = MeetingPermissions.CHANGE


@websocket_incoming_messages("meeting.roles.remove")
class RemoveMeetingRoles(AbstractChangeRoles):
    class Config:
        model = Meeting
        action = "remove"
        permission = MeetingPermissions.CHANGE


# ETC all other contexts
