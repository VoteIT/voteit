from __future__ import annotations

from logging import getLogger

from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.messaging.abcs import AbstractObjectChannel
from voteit.messaging.decorators import channel

logger = getLogger(__name__)


@channel
class MeetingChannel(AbstractObjectChannel):
    """This transmits messages for

    - Polls
    - Non-private Agenda (The title and order of agenda items)
    - Anything public related to the meeting
    """

    name = "meeting"
    logger = logger
    model = Meeting
    permission = MeetingPermissions.VIEW


# FIXME: Private agenda items
@channel
class ModeratorChannel(AbstractObjectChannel):
    """Moderator specific messages

    Transport for:
    - private agenda items
    - Updates for things that only moderators need to know (The number of present users for instance)
    """

    name = "moderator"
    logger = logger
    model = Meeting
    permission = MeetingPermissions.MODERATE
