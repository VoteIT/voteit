from __future__ import annotations

from logging import getLogger

from envelope.core.channels import ContextChannel

from voteit.messaging.decorators import channel
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.permissions import SpeakerSystemPermissions

logger = getLogger(__name__)


@channel
class SpeakerListSystemChannel(ContextChannel):
    """
    This channel if only for speaker list handlers.
    It pushes data that only speaker moderators need, like exactly how many seconds someone spoken.
    """

    name = "sls"
    logger = logger
    model = SpeakerListSystem
    permission = SpeakerSystemPermissions.VIEW
