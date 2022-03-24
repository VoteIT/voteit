from __future__ import annotations

from logging import getLogger

from envelope.core.channels import ContextChannel

from .models import Organisation
from .permissions import OrgPermissions
from voteit.messaging.decorators import channel

logger = getLogger(__name__)


@channel
class OrganisationChannel(ContextChannel):
    """This is the generic meeting channel, everyone should subscribe to this.
    Anything meant to reach anyone interacting with the meeting should be published here.
    """

    name = "organisation"
    logger = logger
    model = Organisation
    permission = OrgPermissions.VIEW
