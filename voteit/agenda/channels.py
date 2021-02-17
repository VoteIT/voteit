from __future__ import annotations

from logging import getLogger

from voteit.agenda.models import AgendaItem
from voteit.agenda.permissions import AgendaPermissions
from voteit.messaging.abcs import AbstractObjectChannel
from voteit.messaging.decorators import channel

logger = getLogger(__name__)


@channel
class AgendaItemChannel(AbstractObjectChannel):
    """This contains generic messages for the agenda item.

    - Proposals
    - Discussions
    - Any metadata around those

    Agenda Items themselves go in the meeting channel
    """

    name = "agenda_item"
    logger = logger
    model = AgendaItem
    permission = AgendaPermissions.VIEW
