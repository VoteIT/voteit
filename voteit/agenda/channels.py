from __future__ import annotations

from logging import getLogger

from envelope.core.channels import ContextChannel

from voteit.agenda.models import AgendaItem
from voteit.agenda.permissions import AgendaPermissions
from voteit.messaging.decorators import channel

logger = getLogger(__name__)


@channel
class AgendaItemChannel(ContextChannel):
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
