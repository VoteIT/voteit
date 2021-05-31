from django.http import Http404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.viewsets import ViewSet

from voteit.core.component import Registry
from voteit.messaging.rest_api import serializers

__all__ = ["IncomingViewSet", "OutgoingViewSet"]

from voteit.messaging.utils import get_incoming_registry
from voteit.messaging.utils import get_outgoing_registry


class MessageIntrospectionViewSet(ViewSet):
    serializer_class: Serializer
    registry: Registry
    permission_classes = [AllowAny]

    def list(self, request, *args, **kwargs):
        serializer = self.serializer_class(
            self.registry.values(), many=True, context={"request": request}
        )
        return Response(serializer.data)

    # FIXME: Retrieve doesn't work
    def retrieve(self, request, pk=None):
        if pk in self.registry:
            serializer = self.serializer_class(
                self.registry[pk], context={"request": request}
            )
            return Response(serializer.data)
        raise Http404()


class IncomingViewSet(MessageIntrospectionViewSet):
    serializer_class = serializers.IncomingMessageSerializer

    @property
    def registry(self):
        return get_incoming_registry()


class OutgoingViewSet(MessageIntrospectionViewSet):
    serializer_class = serializers.OutgoingMessageSerializer

    @property
    def registry(self):
        return get_outgoing_registry()
