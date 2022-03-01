from voteit.agenda.models import AgendaItem
from voteit.agenda.rest_api import serializers
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.meeting.models import Meeting


class AgendaViewSet(DefaultModelViewSet):
    serializer_class = serializers.AgendaItemSerializer
    serializer_classes = {"create": serializers.CreateAgendaItemSerializer}
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"
    queryset = AgendaItem.objects.all()
    model = AgendaItem
