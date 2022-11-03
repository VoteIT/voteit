from __future__ import annotations

from typing import OrderedDict
from typing import TYPE_CHECKING

from pydantic.main import BaseModel

from envelope.core.message import AsyncRunnable
from envelope.core.message import Message
from voteit.core.utils import get_available_transitions
from voteit.messaging.decorators import incoming
from voteit.messaging.decorators import outgoing

if TYPE_CHECKING:
    from envelope.consumers.websocket import WebsocketConsumer


@incoming
class GetAllTransitions(AsyncRunnable):
    """All transitions in VoteIT regardless of conditions or permissions."""

    name = "transitions.get"

    async def run(self, *, consumer: WebsocketConsumer, **kwargs) -> AllTransitions:
        response = AllTransitions.from_message(
            self, transitions=get_available_transitions()
        )
        await consumer.send_ws_message(response, state=response.SUCCESS)
        return response


class TransitionsSchema(BaseModel):
    transitions: dict[str, list[OrderedDict]]


@outgoing
class AllTransitions(Message):
    name = "transitions.all"
    schema = TransitionsSchema
    data: TransitionsSchema
