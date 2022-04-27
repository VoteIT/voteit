from logging import getLogger

from django.db import models
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.mixins import ListModelMixin
from rest_framework.viewsets import GenericViewSet
from rest_framework import exceptions
from rest_framework.permissions import IsAuthenticated

from voteit.core.rest_api import router
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.core.rest_api.mixins import ModelContextMixin
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.permissions import SpeakerSystemPermissions
from voteit.speaker.rest_api import serializers
from voteit.speaker.rest_api.filters import SpeakerFilterSet
from voteit.speaker.roles import ROLE_LIST_MODERATOR


logger = getLogger(__name__)


@router.register("speaker-lists", basename="speaker-lists")
class SpeakerListViewSet(DefaultModelViewSet):
    model = SpeakerList
    queryset = SpeakerList.objects.all()
    serializer_class = serializers.SpeakerListSerializer
    serializer_classes = {"historic": serializers.HistoricSpeakerListSerializer}
    context_lookup_kwarg: str = "speaker_system"
    context_lookup_field: str = "pk"
    context_queryset = SpeakerListSystem.objects.all()

    def get_queryset(self):
        if self.detail:
            return self.queryset
        try:
            speaker_system = self.get_context(self.request)
        except exceptions.ValidationError:
            speaker_system = None
        if speaker_system and self.request.user.has_perm(
            SpeakerSystemPermissions.VIEW, speaker_system
        ):
            return self.queryset.filter(speaker_system=speaker_system)
        return self.queryset.none()


@router.register("speaker-history", basename="speaker-history")
class HistoricSpeakerViewSet(
    ModelContextMixin,
    ListModelMixin,
    GenericViewSet,
):
    model = Speaker
    queryset = (
        Speaker.objects.filter(
            seconds__isnull=False,
        )
        .values(
            "user",
        )
        .annotate(
            times_spoken=models.Count("user"),
            seconds_spoken=models.Sum("seconds"),
        )
    )
    serializer_class = serializers.HistoricSpeakerListSerializer
    filter_backends = (DjangoFilterBackend,)
    filterset_class = SpeakerFilterSet
    permission_classes = (IsAuthenticated,)
    context_lookup_kwarg = "meeting"
    context_queryset = Meeting.objects.all()

    def get_queryset(self):
        if self.detail:
            return self.queryset
        try:
            meeting = self.get_context(self.request)
        except exceptions.ValidationError:
            meeting = None
        if meeting and self.request.user.has_perm(MeetingPermissions.VIEW, meeting):
            return self.queryset.filter(speaker_list__speaker_system__meeting=meeting)
        return self.queryset.none()


@router.register("speaker-list-systems")
class SpeakerListSystemViewSet(DefaultModelViewSet):
    model = SpeakerListSystem
    queryset = SpeakerListSystem.objects.all()
    serializer_class = serializers.SpeakerListSystemSerializer
    context_lookup_kwarg: str = "meeting"
    context_lookup_field: str = "pk"
    context_queryset = Meeting.objects.all()
    context_permission = MeetingPermissions.VIEW

    def perform_create(self, serializer):
        instance: SpeakerListSystem = serializer.save()
        instance.add_roles(self.request.user, ROLE_LIST_MODERATOR)

    def get_queryset(self):
        if self.detail:
            return self.queryset
        try:
            meeting = self.get_context(self.request)
        except exceptions.ValidationError:
            meeting = None
        if meeting and self.request.user.has_perm(MeetingPermissions.VIEW, meeting):
            return self.queryset.filter(meeting=meeting)
        self.queryset.none()
