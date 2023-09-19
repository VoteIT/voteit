from __future__ import annotations

from logging import getLogger

from envelope.channels.models import ContextChannel
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.messaging.decorators import channel

logger = getLogger(__name__)


@channel
class MeetingInvitesChannel(ContextChannel):
    """
    This is a channel that's only for moderators. It handles invites and status updates from them.
    """

    name = "invites"
    logger = logger
    model = Meeting
    permission = MeetingPermissions.MODERATE
