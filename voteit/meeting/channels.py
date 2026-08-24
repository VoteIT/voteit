from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from voteit.messaging.channels import ContextChannel

from voteit.core import PERM
from voteit.meeting.models import Meeting
from voteit.messaging.decorators import channel

if TYPE_CHECKING:
    from chanx.messages.base import BaseMessage

logger = getLogger(__name__)


@channel
class ParticipantsChannel(ContextChannel):
    """This transmits messages for regular participants that aren't moderators.
        Moderators should NOT subscribe to this channel,
        since the messages there will conflict the moderator channel.

    - Non-private polls
    - Non-private Agenda (The title and order of agenda items)
    - Everything meeting-wide, via :func:`broadcast_meeting`
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
    - Everything meeting-wide, via :func:`broadcast_meeting`
    """

    name = "moderators"
    logger = logger
    model = Meeting
    permission = Meeting.get_perm(PERM.MODERATE)


def broadcast_meeting(
    meeting: Meeting | int, message: BaseMessage, *, on_commit: bool = True
) -> None:
    """Publish to everyone interacting with the meeting, moderator or not.

    The two channels partition the audience -- ``moderators`` requires MODERATE,
    which implies the VIEW that ``participants`` requires -- so publishing to
    both reaches every subscriber exactly once.

    This replaces the old ``meeting`` channel. That channel existed only so
    clients had one place to hear meeting-wide news, but its permission was
    *identical* to ``participants``, so it never reached anyone the other two
    could not. What it did cost was a second ``channel.subscribe``, a second RQ
    job and a second app state snapshot -- two snapshots that could interleave,
    letting a client see ``agenda.items`` before ``meeting.roles``.

    ``meeting`` may be a Meeting or a bare pk; pass whichever the caller already
    holds, since only the pk is ever read.
    """
    pk = meeting if isinstance(meeting, int) else meeting.pk
    for channel_cls in (ParticipantsChannel, ModeratorsChannel):
        channel_cls(pk).sync_publish(message, on_commit=on_commit)
