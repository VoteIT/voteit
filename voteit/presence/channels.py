from logging import getLogger

from envelope.core.channels import ContextChannel

from voteit.messaging.decorators import channel
from voteit.presence.permissions import PresenceCheckPermissions
from voteit.presence.models import PresenceCheck


logger = getLogger(__name__)


@channel
class PresenceCheckChannel(ContextChannel):
    """A channel for specific presence check updates.


    (Presence check objects are part of the meeting channel)
    """

    name = "presence_check"
    permission = PresenceCheckPermissions.VIEW
    logger = logger
    model = PresenceCheck
