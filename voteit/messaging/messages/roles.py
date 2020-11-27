from __future__ import annotations

from typing import List

from django.contrib.auth import get_user_model
from pydantic import validator
from django.utils.translation import gettext as _
from voteit.core.role import RoleOutput

from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.messaging.messages.abcs import AbstractContextJobMessage, ContextJobDefault, AbstractConsumerMessage, AbstractOutgoingMessage
from voteit.messaging.messages.text import TextMessage
from voteit.messaging.registries import websocket_incoming_messages, websocket_outgoing_messages
from voteit.core.models import RoleContextMixin, Role
from voteit.speaker.models import SpeakerListSystem


User = get_user_model()


class ChangeRolesBase(AbstractContextJobMessage):
    userids: List[int]  # Validation deferred to job
    roles: List[str]

    @validator("roles")
    def validate_roles(cls, v: List[str]):
        if issubclass(cls.Job.model, RoleContextMixin):
            ValueError(f"{cls} isn't configured correctly, it needs a Job.model")
        valid = cls.Job.model.roles_cls.valid_roles
        for role in v:
            if role not in valid:
                raise ValueError(f"{role} is not a valid role for {cls.Job.model}")
        return v

    def job(self):
        user = self.get_user()
        context = self.get_context()
        if self.allowed(user, context):
            users_qs = User.objects.filter(pk__in=self.userids)
            if len(self.userids) != users_qs.count():
                msg = TextMessage(message=_("Some userids don't exist"))
                msg.send(
                    channel=self.mc.consumer_name,
                    message_id=self.mc.message_id,
                    success=False,
                )
                return
            if self.Job.action == "add":
                method = context.add_roles
                text = _("Added %(count)s" % {"count": len(self.userids)})
            elif self.Job.action == "remove":
                method = context.remove_roles
                text = _("Removed %(count)s" % {"count": len(self.userids)})
            else:
                raise ValueError("Action must be 'add' or 'remove'")
            for usr in User.objects.filter(pk__in=self.userids):
                method(usr, *self.roles)
            msg = TextMessage(message=text)
            msg.send(
                channel=self.mc.consumer_name,
                message_id=self.mc.message_id,
                success=True,
            )
        else:  # Not allowed
            msg = TextMessage(message="Not allowed")
            msg.send(
                channel=self.mc.consumer_name,
                message_id=self.mc.message_id,
                success=False,
            )


@websocket_incoming_messages("meeting.roles.add")
class AddMeetingRoles(ChangeRolesBase):
    class Job(ContextJobDefault):
        model = Meeting
        action = "add"
        permission = MeetingPermissions.CHANGE


@websocket_incoming_messages("meeting.roles.remove")
class RemoveMeetingRoles(ChangeRolesBase):
    class Job(ContextJobDefault):
        model = Meeting
        action = "remove"
        permission = MeetingPermissions.CHANGE


# ETC...


class AvailableRolesBase(AbstractConsumerMessage):
    async def consume(self, consumer):
        valid = self.Job.model.roles_cls.valid_roles
        roles = [r.as_output() for r in valid.values()]
        msg = ResponseAvailableRoles(role_ids=list(valid), roles=roles)
        await msg.async_send(consumer.channel_name, message_id=self.mc.message_id, success=True)

@websocket_outgoing_messages("roles.available")
class ResponseAvailableRoles(AbstractOutgoingMessage):
    role_ids: List[str]
    roles: List[RoleOutput]


@websocket_incoming_messages("meeting.roles.available")
class AvailableMeetingRoles(AvailableRolesBase):
    class Job:
        model = Meeting


@websocket_incoming_messages("speaker_list_system.roles.available")
class AvailableSpeakerSystemRoles(AvailableRolesBase):
    class Job:
        model = SpeakerListSystem


# ETC all other contexts
