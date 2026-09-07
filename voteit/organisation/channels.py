from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from voteit.messaging.channels import ContextChannel

from .models import Organisation
from voteit.messaging.decorators import channel

if TYPE_CHECKING:
    from chanx.messages.base import BaseMessage

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


def broadcast_organisation(
    message: BaseMessage,
    organisation: Organisation | int | None = None,
    *,
    on_commit: bool = True,
) -> list[int]:
    """Publish to everyone connected, optionally narrowed to one organisation.

    Every authenticated socket joins its own organisation's channel while
    connecting, so the group *is* the organisation filter.
    Returns the pks published to.
    """
    if organisation is None:
        pks = list(
            Organisation.objects.filter(active=True).values_list("pk", flat=True)
        )
    else:
        pks = [
            organisation if isinstance(organisation, int) else organisation.pk,
        ]
    for pk in pks:
        OrganisationChannel(pk).sync_publish(message, on_commit=on_commit)
    return pks
