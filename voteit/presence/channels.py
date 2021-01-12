from logging import getLogger

from voteit.messaging.abcs import AbstractObjectChannel
from voteit.messaging.decorators import channel
from voteit.presence.permissions import PresenceCheckPermissions
from voteit.presence.models import PresenceCheck


logger = getLogger(__name__)


@channel
class PresenceCheckChannel(AbstractObjectChannel):
    """ A channel for specific presence check updates.


        (Presence check objects are part of the meeting channel)
    """
    name = "presence_check"
    permission = PresenceCheckPermissions.VIEW
    logger = logger
    model = PresenceCheck
