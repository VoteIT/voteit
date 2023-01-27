from __future__ import annotations

from logging import getLogger

from envelope.core.channels import ContextChannel

from voteit.messaging.decorators import channel
from voteit.poll.models import Poll
from voteit.poll.permissions import PollPermissions

logger = getLogger(__name__)


@channel
class PollChannel(ContextChannel):
    """A channel for specific poll updates.

    Transport for
    - Voting

    (Poll objects themselves are part of the meeting channel)
    """

    name = "poll"
    permission = PollPermissions.VIEW
    logger = logger
    model = Poll
