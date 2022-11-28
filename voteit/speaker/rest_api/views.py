import csv
from logging import getLogger

from django.db import models
from django.http import Http404
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.mixins import DestroyModelMixin
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.mixins import UpdateModelMixin
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework import exceptions
from rest_framework import permissions

from voteit.core.decorators import has_perm_drf
from voteit.core.rest_api import router
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.core.rest_api.mixins import AutoPermissionViewSetMixin
from voteit.core.rest_api.mixins import ModelContextMixin
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.permissions import SpeakerListPermissions
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
    permission_classes = (permissions.IsAuthenticated,)
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


@router.register("speaker-list-systems", basename="speaker-list-systems")
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


@router.register("speakers", basename="speakers")
class SpeakerViewSet(
    AutoPermissionViewSetMixin,
    ModelContextMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    DestroyModelMixin,
    ListModelMixin,
    GenericViewSet,
):
    """
    REST interface to fetch speakers that have already spoken.
    Either to view the list or to modify them in case something went wrong.
    """

    model = Speaker
    queryset = Speaker.objects.filter(seconds__isnull=False)
    serializer_class = serializers.SpeakerSerializer
    context_lookup_kwarg: str = "speaker_list"
    context_lookup_field: str = "pk"
    context_queryset = SpeakerList.objects.all()

    def get_queryset(self):
        if self.detail:
            return self.queryset
        try:
            speaker_list = self.get_context(self.request)
        except exceptions.ValidationError:
            speaker_list = None
        if speaker_list and self.request.user.has_perm(
            SpeakerListPermissions.VIEW, speaker_list
        ):
            return self.queryset.filter(speaker_list=speaker_list)
        return self.queryset.none()


@router.register("export-speakers", basename="export-speakers")
class ExportSpeakersViewSet(viewsets.GenericViewSet):
    model = SpeakerListSystem
    permission_classes = [permissions.IsAuthenticated]
    queryset = SpeakerListSystem.objects.all()

    def list(self, request):
        return Response()

    def get_export_qs(self, sls: SpeakerListSystem):
        return (
            Speaker.objects.filter(speaker_list__speaker_system=sls)
            .exclude(seconds__isnull=True)
            .order_by("started")
            .annotate(
                first_name=models.F("user__first_name"),
                last_name=models.F("user__last_name"),
                email=models.F("user__email"),
                userid=models.F("user__userid"),
            )
        )

    @action(
        methods=["get"],
        detail=True,
        serializer_class=serializers.SpeakerExportSerializer,
    )
    @has_perm_drf(SpeakerSystemPermissions.MANAGE)
    def csv(self, request, *args, **kwargs):
        sls = self.get_object()
        serializer = self.get_serializer(self.get_export_qs(sls), many=True)
        if not serializer.data:
            raise Http404("No data yet")
        response = HttpResponse(content_type="text/csv")
        response[
            "Content-Disposition"
        ] = f'attachment; filename="speakers_sls{sls.pk}_export.csv"'
        writer = csv.DictWriter(response, fieldnames=serializer.data[0].keys())
        writer.writeheader()
        for row in serializer.data:
            writer.writerow(row)
        return response

    @action(
        methods=["get"],
        detail=True,
        serializer_class=serializers.SpeakerExportSerializer,
        renderer_classes=[JSONRenderer],
    )
    @has_perm_drf(SpeakerSystemPermissions.MANAGE)
    def json(self, request, *args, **kwargs):
        sls = self.get_object()
        serializer = self.get_serializer(self.get_export_qs(sls), many=True)
        return Response(
            serializer.data,
            headers={
                "Content-Disposition": f'attachment; filename="speakers_sls{sls.pk}_export.json"'
            },
        )
