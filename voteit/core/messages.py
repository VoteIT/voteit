from __future__ import annotations
from typing import OrderedDict
from typing import TYPE_CHECKING

from pydantic.main import BaseModel
from typing import List

from typing import Dict

from voteit.core.utils import get_available_transitions
from voteit.messaging.abcs import AsyncRunnable
from voteit.messaging.abcs import BaseIncomingMessage
from voteit.messaging.abcs import BaseOutgoingMessage
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing

if TYPE_CHECKING:
    from voteit.messaging.consumers import WebsocketDemuxConsumer


class RolesChangeSchema(BaseModel):
    """
    Roles changed, either added or removed.

    model is the class name an pk the primary key of the context where the change happened.
    """

    user_pk: int
    roles: List[str]
    pk: int  # context where the change happened, use together with model
    model: str  # The model shortname


@outgoing
class RolesAdded(BaseOutgoingMessage):
    name = "roles.added"
    schema = RolesChangeSchema
    data: RolesChangeSchema


@outgoing
class RolesRemoved(BaseOutgoingMessage):
    name = "roles.removed"
    schema = RolesChangeSchema
    data: RolesChangeSchema


@incoming
class GetAllTransitions(BaseIncomingMessage, AsyncRunnable):
    """ All transitions in VoteIT regardless of conditions or permissions."""

    name = "transitions.get"

    async def run(self, consumer: WebsocketDemuxConsumer) -> AllTransitions:
        response = AllTransitions.from_message(
            self, transitions=get_available_transitions()
        )
        await response.async_send_outgoing(
            channel_name=self.mm.consumer_name, success=True
        )
        return response


class TransitionsSchema(BaseModel):
    transitions: Dict[str, List[OrderedDict]]


@outgoing
class AllTransitions(BaseOutgoingMessage):
    name = "transitions.all"
    schema = TransitionsSchema
    data: TransitionsSchema
