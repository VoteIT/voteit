from __future__ import annotations

from voteit.invites.schemas import InviteAddedOrUpdatedSchema
from voteit.messaging.base import BaseObjectAdded
from voteit.messaging.base import BaseObjectChanged
from voteit.messaging.base import BaseObjectDeleted
from voteit.messaging.decorators import outgoing


@outgoing
class MeetingInviteAdded(BaseObjectAdded):
    name = "meeting_invite.added"
    schema = InviteAddedOrUpdatedSchema
    data: InviteAddedOrUpdatedSchema


@outgoing
class MeetingInviteChanged(BaseObjectChanged):
    name = "meeting_invite.changed"
    schema = InviteAddedOrUpdatedSchema
    data: InviteAddedOrUpdatedSchema


@outgoing
class MeetingInviteDeleted(BaseObjectDeleted):
    name = "meeting_invite.deleted"
