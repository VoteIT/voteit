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
from rest_framework.generics import get_object_or_404
from rest_framework.mixins import ListModelMixin
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.viewsets import GenericViewSet

from voteit.core import PERM
from voteit.core.loggers import log_roles_change
from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import TransitionsMixin
from voteit.core.rest_api.mixins import VerboseAutoPermissionViewSetMixin
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.models import SpeakerSystemRoles
from voteit.speaker.rest_api import serializers
from voteit.speaker.rest_api.filters import SpeakerFilterSet
from voteit.speaker.rest_api.filters import SpeakerSystemRolesFilterSet
from voteit.speaker.roles import ROLE_LIST_MODERATOR

logger = getLogger(__name__)


@router.register("speaker-lists", basename="speaker-lists")
class SpeakerListViewSet(
    VerboseAutoPermissionViewSetMixin, TransitionsMixin, viewsets.ModelViewSet
):
    model = SpeakerList
    serializer_class = serializers.SpeakerListSerializer
    serializer_classes = {"create": serializers.CreateSpeakerListSerializer}
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "create": None,  # In serializer
        "enter": "enter",
        "leave": None,  # No permission check required
        "shuffle": "shuffle",
        "retrieve": None,  # Checked via qs
    }

    def get_queryset(self):
        if self.detail:
            return SpeakerList.objects.filter(
                meeting__participants=self.request.user,
            )
        return SpeakerList.objects.none()

    def get_update_object(self):
        queryset = self.filter_queryset(
            self.get_queryset().select_for_update().filter(pk=self.kwargs["pk"])
        )
        return get_object_or_404(queryset)

    @action(methods=["POST"], detail=True, serializer_class=Serializer)
    @transaction.atomic(durable=True)
    def enter(self, request, *args, **kwargs):
        speaker_list: SpeakerList = self.get_update_object()
        speaker, created = speaker_list.speaker_items.get_or_create(
            user=request.user, started=None
        )
        if created:
            speaker_list.reorder()
        serializer = serializers.SpeakerSerializer(
            speaker, context=self.get_serializer_context()
        )
        return Response(serializer.data, status=201 if created else 200)

    @action(methods=["POST"], detail=True, serializer_class=Serializer)
    @transaction.atomic(durable=True)
    def leave(self, request, *args, **kwargs):
        instance: SpeakerList = self.get_update_object()
        was_deleted, _ = instance.speakers_in_queue().filter(user=request.user).delete()
        if was_deleted:
            instance.reorder()
            return Response(status=204)
        raise NotFound()

    @action(methods=["POST"], detail=True)
    @transaction.atomic(durable=True)
    def shuffle(self, request, *args, **kwargs):
        instance: SpeakerList = self.get_update_object()
        if instance.active_speaker():
            raise PermissionDenied(_("Shuffle isn't allowed with an active speaker."))
        instance.shuffle()
        return Response(status=200)


@router.register("speaker-history", basename="speaker-history")
class HistoricSpeakerViewSet(
    ListModelMixin,
    GenericViewSet,
):
    expected_default_http_status = 400
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
    filterset_class = SpeakerFilterSet
    permission_classes = (permissions.IsAuthenticated,)


@router.register("speaker-list-systems", basename="speaker-list-systems")
class SpeakerListSystemViewSet(
    VerboseAutoPermissionViewSetMixin,
    TransitionsMixin,
    viewsets.ModelViewSet,
):
    model = SpeakerListSystem
    serializer_class = serializers.SpeakerListSystemSerializer
    serializer_classes = {"create": serializers.CreateSpeakerListSystemSerializer}
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "create": None,  # Handled in serializer
        "retrieve": None,  # Already checked in qs
    }

    def get_queryset(self):
        if self.detail:
            return SpeakerListSystem.objects.filter(
                meeting__participants=self.request.user,
            )
        return SpeakerListSystem.objects.none()


@router.register("speaker-system-roles", basename="speaker-system-roles")
class SpeakerSystemRolesViewSet(ListModelMixin, GenericViewSet):
    serializer_class = serializers.SpeakerSystemRolesSerializer
    permission_classes = (permissions.IsAuthenticated,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = SpeakerSystemRolesFilterSet

    def get_queryset(self):
        if not self.request.query_params.get("speaker_system"):
            return SpeakerSystemRoles.objects.none()
        return SpeakerSystemRoles.objects.filter(
            context__meeting__participants=self.request.user
        ).prefetch_related("user")

    @action(detail=False, methods=["get"], permission_classes=[])
    def available(self, request):
        return Response(
            [
                role.output().dict(exclude={"predicate_info"})
                for role in SpeakerSystemRoles.valid_roles.values()
            ]
        )

    @action(
        detail=False,
        methods=["post"],
        serializer_class=serializers.SpeakerChangeRolesSerializer,
    )
    @transaction.atomic
    def add_roles(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        system = serializer.validated_data["speaker_system"]
        user = serializer.validated_data["user"]
        if not request.user.has_perm(
            SpeakerListSystem.get_perm(PERM.CHANGE_ROLES), system
        ):
            raise PermissionDenied
        changed = system.add_roles(user, *serializer.validated_data["roles"])
        if changed:
            log_roles_change(
                "Added",
                actor=request.user,
                for_user=user,
                context=system,
                roles=changed,
            )
        roles_obj = SpeakerSystemRoles.objects.get(context=system, user=user)
        return Response(serializers.SpeakerSystemRolesSerializer(roles_obj).data)

    @action(
        detail=False,
        methods=["post"],
        serializer_class=serializers.SpeakerChangeRolesSerializer,
    )
    @transaction.atomic
    def remove_roles(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        system = serializer.validated_data["speaker_system"]
        user = serializer.validated_data["user"]
        if not request.user.has_perm(
            SpeakerListSystem.get_perm(PERM.CHANGE_ROLES), system
        ):
            raise PermissionDenied
        changed = system.remove_roles(user, *serializer.validated_data["roles"])
        if changed:
            log_roles_change(
                "Removed",
                actor=request.user,
                for_user=user,
                context=system,
                roles=changed,
            )
        try:
            roles_obj = SpeakerSystemRoles.objects.get(context=system, user=user)
        except SpeakerSystemRoles.DoesNotExist:
            return Response(status=204)
        return Response(serializers.SpeakerSystemRolesSerializer(roles_obj).data)


@router.register("speakers", basename="speakers")
class SpeakerViewSet(
    VerboseAutoPermissionViewSetMixin,
    TransitionsMixin,
    viewsets.ModelViewSet,
):
    model = Speaker
    serializer_class = serializers.SpeakerSerializer
    serializer_classes = {
        "create": serializers.CreateSpeakerSerializer,
    }
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "create": None,  # In serializer
        "start": "start",  # Handled by qs
        "stop": None,  # Handled by qs
        "undo": None,  # Handled by qs
        "retrieve": None,  # Handled by qs
    }

    def get_queryset(self):
        if self.detail:
            qs = (
                Speaker.objects.filter(
                    models.Q(
                        speaker_list__meeting__roles__user=self.request.user,
                        speaker_list__meeting__roles__assigned__contains=ROLE_MODERATOR,
                    )
                    | models.Q(
                        speaker_list__speaker_system__speakersystemroles__user=self.request.user,
                        speaker_list__speaker_system__speakersystemroles__assigned__contains=ROLE_LIST_MODERATOR,
                    )
                )
                .select_related(
                    "speaker_list",
                    "user",
                )
                .distinct()
            )
            if self.action in ("start", "leave"):
                return qs.filter(seconds__isnull=True, started__isnull=True)
            elif self.action in ("stop", "undo"):
                return qs.filter(seconds__isnull=True, started__isnull=False)
            elif self.action in ("update", "partial_update"):
                # Only modify closed speakers
                return qs.filter(seconds__isnull=False, started__isnull=False)
            return qs
        return Speaker.objects.none()

    def _get_locked_sl(self, pk: int) -> SpeakerList:
        return SpeakerList.objects.select_for_update().get(pk=pk)

    def perform_create(self, serializer):
        with transaction.atomic(durable=True):
            speaker_list = self._get_locked_sl(
                serializer.validated_data["speaker_list"].pk
            )
            serializer.save()
            speaker_list.reorder()

    def perform_destroy(self, instance: Speaker):
        with transaction.atomic(durable=True):
            speaker_list = self._get_locked_sl(instance.speaker_list_id)
            instance.delete()
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
                speaker_list.order_list = [
                    u for u in speaker_list.order_list if u != speaker.user_id
                ]
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

    def get_queryset(self):
        return SpeakerListSystem.objects.filter(
            models.Q(
                meeting__roles__user=self.request.user,
                meeting__roles__assigned__contains=ROLE_MODERATOR,
            )
            | models.Q(
                speakersystemroles__user=self.request.user,
                speakersystemroles__assigned__contains=ROLE_LIST_MODERATOR,
            )
        ).distinct()

    def list(self, request):  # pragma: no coverage
        return Response(data=[])

    def get_export_qs(self, sls: SpeakerListSystem):
        return (
            Speaker.objects.filter(speaker_list__speaker_system=sls)
            .exclude(seconds__isnull=True)
            .select_related("speaker_list", "user", "speaker_list__agenda_item")
            .order_by("started")
        )

    @action(
        methods=["get"],
        detail=True,
        serializer_class=serializers.SpeakerExportSerializer,
    )
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
    def json(self, request, *args, **kwargs):
        sls = self.get_object()
        serializer = self.get_serializer(self.get_export_qs(sls), many=True)
        return Response(
            serializer.data,
            headers={
                "Content-Disposition": f'attachment; filename="speakers_sls{sls.pk}_export.json"'
            },
        )
