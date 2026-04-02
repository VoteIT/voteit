from __future__ import annotations

from logging import getLogger

from envelope.channels.models import ContextChannel

from voteit.core import PERM
from voteit.messaging.decorators import channel
from voteit.room.models import Room

logger = getLogger(__name__)


@channel
class RoomChannel(ContextChannel):
    """
    The more room-specific things we want to send to users.
    """

    name = "room"
    logger = logger
    model = Room
    permission = Room.get_perm(PERM.VIEW)
