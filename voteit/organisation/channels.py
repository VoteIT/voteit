from __future__ import annotations

from logging import getLogger

from envelope.channels.models import ContextChannel

from .models import Organisation
from voteit.messaging.decorators import channel

logger = getLogger(__name__)


@channel
class OrganisationChannel(ContextChannel):
    """This is the generic organisation channel. Should be subscribed to for live updates of org roles.
    It also sends organisation object changes.
    """

    name = "organisation"
    logger = logger
    model = Organisation
    permission = None
