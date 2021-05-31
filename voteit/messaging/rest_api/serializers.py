from django.urls import reverse
from rest_framework import serializers


# __all__ = ("MessageIntrospectionSerializer",)

from voteit.messaging.abcs import AsyncRunnable
from voteit.messaging.abcs import DeferredJob


class MessageIntrospectionSerializer(serializers.Serializer):
    name = serializers.CharField()
    schema = serializers.SerializerMethodField()
    async_runnable = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()
    view_name: str

    def get_async_runnable(self, msg_type):
        return issubclass(msg_type, AsyncRunnable)

    def get_schema(self, msg_type):
        if msg_type.schema is not None:
            return msg_type.schema.schema()

    def get_url(self, msg_type):
        if "request" in self.context:
            request = self.context["request"]
            # path = reverse(self.view_name, kwargs={"pk": msg_type.name})
            path = f"{reverse(self.view_name)}{msg_type.name}/"  # FIXME: Use reverse properly
            return request.build_absolute_uri(path)


class IncomingMessageSerializer(MessageIntrospectionSerializer):
    view_name = "incoming-messages-list"

    deferred_job = serializers.SerializerMethodField()

    def get_deferred_job(self, msg_type):
        return issubclass(msg_type, DeferredJob)


class OutgoingMessageSerializer(MessageIntrospectionSerializer):
    view_name = "outgoing-messages-list"
