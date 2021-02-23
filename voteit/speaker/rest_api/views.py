from rest_framework import (
    viewsets,
    mixins,
)

from voteit.core.rest_api.mixins import CreateModelPermissionsMixin
from voteit.core.rest_api.mixins import TransitionsMixin
from voteit.meeting.models import Meeting
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.rest_api import serializers
from voteit.speaker.roles import ROLE_LIST_MODERATOR


class SpeakerListViewSet(
    CreateModelPermissionsMixin,
    TransitionsMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    model = SpeakerList
    queryset = SpeakerList.objects.all()
    serializer_class = serializers.SpeakerListSerializer
    context_lookup_kwarg: str = "list_system"
    context_lookup_field: str = "pk"
    context_queryset = SpeakerListSystem.objects.all()


class SpeakerListSystemViewSet(
    CreateModelPermissionsMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    model = SpeakerListSystem
    queryset = SpeakerListSystem.objects.all()
    serializer_class = serializers.SpeakerListSystemSerializer
    context_lookup_kwarg: str = "meeting"
    context_lookup_field: str = "pk"
    context_queryset = Meeting.objects.all()

    def perform_create(self, serializer):
        instance: SpeakerListSystem = serializer.save()
        instance.add_roles(self.request.user, ROLE_LIST_MODERATOR)
