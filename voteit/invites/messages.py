from __future__ import annotations

from typing import Literal

from voteit.invites.schemas import InviteAddedOrUpdatedSchema
from voteit.messaging.base import ObjectAddedOrChanged
from voteit.messaging.base import ObjectDeleted
from voteit.messaging.decorators import outgoing


@outgoing
class MeetingInviteChanged(ObjectAddedOrChanged):
    action: Literal["meeting_invite.changed"] = "meeting_invite.changed"
    # Overrides the permissive AddedOrUpdatedSchema base so mask_sensitive
    # actually runs -- without this, raw email/swedish_ssn go out on the wire.
    payload: InviteAddedOrUpdatedSchema


@outgoing
class MeetingInviteDeleted(ObjectDeleted):
    action: Literal["meeting_invite.deleted"] = "meeting_invite.deleted"
