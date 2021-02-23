from rest_framework.viewsets import GenericViewSet

from voteit.agenda.models import AgendaItem
from voteit.agenda.rest_api import serializers
from voteit.core.rest_api.mixins import CreateModelPermissionsMixin, TransitionsMixin
from voteit.meeting.models import Meeting


class AgendaViewSet(CreateModelPermissionsMixin, TransitionsMixin, GenericViewSet):
    serializer_class = serializers.AgendaItemSerializer
    serializer_classes = {
        "list": serializers.AgendaListSerializer,
    }
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"
    queryset = AgendaItem.objects.all()
