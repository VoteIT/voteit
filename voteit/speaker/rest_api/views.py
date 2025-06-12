import csv
from logging import getLogger

from django.db import models
from django.db import transaction
from django.http import Http404
from django.http import HttpResponse
from django.utils.translation import gettext as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import PermissionDenied
from rest_framework.mixins import ListModelMixin
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from voteit.core.decorators import has_perm_drf
from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import AutoPermissionViewSetMixin
from voteit.core.rest_api.mixins import TransitionsMixin
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.permissions import SpeakerSystemPermissions
from voteit.speaker.rest_api import serializers
from voteit.speaker.rest_api.filters import SpeakerFilterSet

logger = getLogger(__name__)


@router.register("speaker-lists", basename="speaker-lists")
class SpeakerListViewSet(
    AutoPermissionViewSetMixin, TransitionsMixin, viewsets.ModelViewSet
):
    model = SpeakerList
    queryset = SpeakerList.objects.all()
    serializer_class = serializers.SpeakerListSerializer
    serializer_classes = {"create": serializers.CreateSpeakerListSerializer}
    permission_type_map = {
        **AutoPermissionViewSetMixin.permission_type_map,
        "leave": None,  # No permission check required
        "shuffle": "shuffle",
    }

    def get_queryset(self):
        if self.detail:
            if self.action in ("leave", "shuffle"):
                return self.queryset.select_for_update()
            return self.queryset
        return self.queryset.none()

    @action(methods=["POST"], detail=True)
    def leave(self, request, *args, **kwargs):
        with transaction.atomic(durable=True):
            instance: SpeakerList = self.get_object()
            was_deleted, _ = (
                instance.speakers_in_queue().filter(user=request.user).delete()
            )
            if was_deleted:
                instance.reorder()
        if was_deleted:
            return Response(status=204)
        raise NotFound()

    @action(methods=["POST"], detail=True)
    def shuffle(self, request, *args, **kwargs):
        with transaction.atomic(durable=True):
            instance: SpeakerList = self.get_object()
            if instance.active_speaker():
                raise PermissionDenied(
                    _("Shuffle isn't allowed with an active speaker.")
                )
            instance.shuffle()
        return Response(status=200)


@router.register("speaker-history", basename="speaker-history")
class HistoricSpeakerViewSet(
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


@router.register("speaker-list-systems", basename="speaker-list-systems")
class SpeakerListSystemViewSet(
    AutoPermissionViewSetMixin,
    TransitionsMixin,
    viewsets.ModelViewSet,
):
    model = SpeakerListSystem
    queryset = SpeakerListSystem.objects.all()
    serializer_class = serializers.SpeakerListSystemSerializer
    serializer_classes = {"create": serializers.CreateSpeakerListSystemSerializer}

    def get_queryset(self):
        if self.action == "list":
            return self.queryset.none()
        return self.queryset


@router.register("speakers", basename="speakers")
class SpeakerViewSet(
    AutoPermissionViewSetMixin,
    TransitionsMixin,
    viewsets.ModelViewSet,
):
    model = Speaker
    queryset = Speaker.objects.all()
    serializer_class = serializers.SpeakerSerializer
    serializer_classes = {
        "create": serializers.CreateSpeakerSerializer,
        "enter": serializers.CreateSpeakerUserImplicitSerializer,
    }
    permission_type_map = {
        **AutoPermissionViewSetMixin.permission_type_map,
        "enter": "enter",  # The normal user version of "add" speaker, user implicit. Also checked in serializer.
        "start": "start",
        "stop": "stop",
        "undo": "undo",
    }

    def get_queryset(self):
        if self.detail:
            detail_qs = self.queryset.select_related(
                "speaker_list",
                "user",
            )
            if self.action in ("start", "leave"):
                return detail_qs.filter(seconds__isnull=True, started__isnull=True)
            elif self.action in ("stop", "undo"):
                return detail_qs.filter(seconds__isnull=True, started__isnull=False)
            elif self.action in ("update", "partial_update"):
                # Only modify closed speakers
                return detail_qs.filter(seconds__isnull=False, started__isnull=False)
            return detail_qs
        return self.queryset.none()

    @action(methods=["POST"], detail=False)
    def enter(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def _get_locked_sl(self, pk: int) -> SpeakerList:
        return SpeakerList.objects.select_for_update().get(pk=pk)

    def perform_create(self, serializer):
        with transaction.atomic(durable=True):
            speaker_list = self._get_locked_sl(
                serializer.validated_data["speaker_list"].pk
            )
            serializer.save()
            speaker_list.reorder()

    @action(methods=["POST"], detail=True)
    def start(self, request, *args, **kwargs):
        speaker = self.get_object()
        if speaker.start():
            speaker.save()
            return Response(status=200)
        return Response(status=400)  # pragma: no coverage

    @action(methods=["POST"], detail=True)
    def stop(self, request, *args, **kwargs):
        speaker = self.get_object()
        if speaker.stop():
            with transaction.atomic(durable=True):
                speaker.save()
                speaker_list = self._get_locked_sl(speaker.speaker_list_id)
                if speaker.user_id in speaker_list.order_list:
                    speaker_list.order_list.remove(speaker.user_id)
                    speaker_list.save()
                return Response(status=200)
        return Response(status=400)  # pragma: no coverage

    @action(methods=["POST"], detail=True)
    def undo(self, request, *args, **kwargs):
        speaker = self.get_object()
        if speaker.undo():
            speaker.save()
            return Response(status=200)
        return Response(status=400)  # pragma: no coverage


@router.register("export-speakers", basename="export-speakers")
class ExportSpeakersViewSet(viewsets.GenericViewSet):
    model = SpeakerListSystem
    permission_classes = [permissions.IsAuthenticated]
    queryset = SpeakerListSystem.objects.all()

    def list(self, request):  # pragma: no coverage
        return Response(data=[])

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
        response["Content-Disposition"] = (
            f'attachment; filename="speakers_sls{sls.pk}_export.csv"'
        )
        writer = csv.DictWriter(response, fieldnames=serializer.child.fields)
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
