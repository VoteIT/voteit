from voteit.core.rest_api.base import DefaultModelViewSet, ReadonlyModelViewSet
from voteit.meeting.models import Meeting
from voteit.presence.models import PresenceSystem, PresenceCheck

from . import serializers


class PresenceSystemViewSet(DefaultModelViewSet):
    serializer_class = serializers.PresenceSystemDetailSerializer
    serializer_classes = {
        "create": serializers.PresenceSystemCreateSerializer,
    }
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"
    model = PresenceSystem
    queryset = PresenceSystem.objects.all()
    # FIXME: Queryset that actually works for list rather than default?


class PresenceCheckViewSet(DefaultModelViewSet):
    serializer_class = serializers.PresenceCheckDetailSerializer
    serializer_classes = {
        "create": serializers.PresenceCheckCreateSerializer,
    }
    context_queryset = PresenceSystem.objects.all()
    context_lookup_kwarg = "presence_system"
    model = PresenceCheck
    queryset = PresenceCheck.objects.all()
