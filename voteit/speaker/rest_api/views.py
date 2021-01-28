from rest_framework import (
    viewsets,
    generics
)

from voteit.core.rest_api.mixins import (
    TransitionsMixin,
    SerializerClassesMixin,
)

from voteit.speaker.models import *
from . import serializers


class SpeakerListViewSet(
    TransitionsMixin,
    SerializerClassesMixin,
    viewsets.ReadOnlyModelViewSet
):
    model = SpeakerList
    queryset = SpeakerList.objects.all()
    serializer_class = serializers.SpeakerListSerializer
