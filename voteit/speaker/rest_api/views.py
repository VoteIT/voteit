from rest_framework.decorators import action
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.core.rest_api.base import ReadonlyModelViewSet
from voteit.meeting.models import Meeting
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.rest_api import serializers
from voteit.speaker.roles import ROLE_LIST_MODERATOR


class SpeakerListViewSet(DefaultModelViewSet):
    model = SpeakerList
    queryset = SpeakerList.objects.all()
    serializer_class = serializers.SpeakerListSerializer
    serializer_classes = {"historic": serializers.HistoricSpeakerListSerializer}
    context_lookup_kwarg: str = "list_system"
    context_lookup_field: str = "pk"
    context_queryset = SpeakerListSystem.objects.all()


class HistoricSpeakerListViewSet(ReadonlyModelViewSet):
    model = SpeakerList
    queryset = SpeakerList.objects.all()
    serializer_class = serializers.HistoricSpeakerListSerializer


class SpeakerListSystemViewSet(DefaultModelViewSet):
    model = SpeakerListSystem
    queryset = SpeakerListSystem.objects.all()
    serializer_class = serializers.SpeakerListSystemSerializer
    context_lookup_kwarg: str = "meeting"
    context_lookup_field: str = "pk"
    context_queryset = Meeting.objects.all()

    def perform_create(self, serializer):
        instance: SpeakerListSystem = serializer.save()
        instance.add_roles(self.request.user, ROLE_LIST_MODERATOR)
