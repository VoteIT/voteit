from rest_framework import (
    viewsets,
)

from voteit.core.rest_api.mixins import (
    TransitionsMixin,
)

from voteit.speaker.models import SpeakerList
from voteit.speaker.rest_api import serializers


class SpeakerListViewSet(TransitionsMixin, viewsets.ReadOnlyModelViewSet):
    model = SpeakerList
    queryset = SpeakerList.objects.all()
    serializer_class = serializers.SpeakerListSerializer
