from __future__ import annotations

from logging import getLogger

from voteit.messaging.channels import ContextChannel

from voteit.core import PERM
from voteit.meeting.models import Meeting
from voteit.messaging.decorators import channel

logger = getLogger(__name__)


@channel
class MeetingChannel(ContextChannel):
    """This is the generic meeting channel, everyone should subscribe to this.
    Anything meant to reach anyone interacting with the meeting should be published here.
    """

    name = "meeting"
    logger = logger
    model = Meeting
    permission = Meeting.get_perm(PERM.VIEW)


@channel
class ParticipantsChannel(ContextChannel):
    """This transmits messages for regular participants that aren't moderators.
        Moderators should NOT subscribe to this channel,
        since the messages there will conflict the moderator channel.

    - Non-private polls
    - Non-private Agenda (The title and order of agenda items)
    """

    name = "participants"
    logger = logger
    model = Meeting
    permission = Meeting.get_perm(PERM.VIEW)


@channel
class ModeratorsChannel(ContextChannel):
    """Moderator messages, moderators should subscribe to this channel instead of the participants channel.

    - All polls
    - All agenda items
    - Updates for things that only moderators need to know
    """

    name = "moderators"
    logger = logger
    model = Meeting
    permission = Meeting.get_perm(PERM.MODERATE)
