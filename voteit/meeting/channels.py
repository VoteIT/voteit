from __future__ import annotations

from logging import getLogger

from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.messaging.abcs import AbstractObjectChannel
from voteit.messaging.decorators import channel

logger = getLogger(__name__)


@channel
class MeetingChannel(AbstractObjectChannel):
    """This is the generic meeting channel, everyone should subscribe to this.
    Anything meant to reach anyone interacting with the meeting should be published here.
    """

    name = "meeting"
    logger = logger
    model = Meeting
    permission = MeetingPermissions.VIEW


@channel
class ParticipantsChannel(AbstractObjectChannel):
    """This transmits messages for regular participants that aren't moderators.
        Moderators should NOT subscribe to this channel,
        since the messages there will conflict the moderator channel.

    - Non-private polls
    - Non-private Agenda (The title and order of agenda items)
    """

    name = "participants"
    logger = logger
    model = Meeting
    permission = MeetingPermissions.VIEW


@channel
class ModeratorsChannel(AbstractObjectChannel):
    """Moderator messages, moderators should subscribe to this channel instead of the participants channel.

    - All polls
    - All agenda items
    - Updates for things that only moderators need to know
    """

    name = "moderators"
    logger = logger
    model = Meeting
    permission = MeetingPermissions.MODERATE
