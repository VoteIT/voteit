from pydantic import validator
from pydantic.main import BaseModel
from typing import Dict

from voteit.messaging.abcs import AsyncRunnable, BaseOutgoingMessage
from voteit.messaging.registries import incoming_messages, outgoing_messages


class GetSchema(BaseModel):
    message_type: str

    @validator("message_type")
    def check_message_type(cls, v):
        v = v.lower()
        if v not in cls.Config.registry:
            raise ValueError(f"'{v}' is not registered as a message type")
        return v


class GetIncomingSchema(GetSchema):
    class Config:
        registry = incoming_messages


class GetOutgoingSchema(GetSchema):
    class Config:
        registry = outgoing_messages


@incoming_messages
class GetSchemaIncomingCommand(AsyncRunnable):
    name = "schema.get_incoming"
    schema = GetIncomingSchema
    data: GetIncomingSchema

    async def run(self, consumer):
        inspected_message = incoming_messages[self.data.message_type]
        response = SendSchema.from_message(
            self, message_schema=inspected_message.schema.schema()
        )
        await response.async_send_outgoing(consumer.channel_name, success=True)


@incoming_messages
class GetSchemaOutgoingCommand(AsyncRunnable):
    name = "schema.get_outgoing"
    schema = GetOutgoingSchema
    data: GetOutgoingSchema

    async def run(self, consumer):
        inspected_message = outgoing_messages[self.data.message_type]
        response = SendSchema.from_message(
            self, message_schema=inspected_message.schema.schema()
        )
        await response.async_send_outgoing(consumer.channel_name, success=True)


class SchemaResponse(BaseModel):
    message_schema: Dict


@outgoing_messages
class SendSchema(BaseOutgoingMessage):
    name = "schema.response"
    schema = SchemaResponse
    data: SchemaResponse
