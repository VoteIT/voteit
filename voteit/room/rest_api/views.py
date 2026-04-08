from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db import transaction
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from voteit.core import PERM
from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import VerboseAutoPermissionViewSetMixin
from voteit.meeting.rest_api.filters import ForceMeetingWithRoleFilter
from voteit.room import ROOM_PERM_HANDLE_SPEAKER
from voteit.room.models import Room
from voteit.room.rest_api.serializers import CreateRoomSerializer
from voteit.room.rest_api.serializers import RoomDetailSerializer
from voteit.room.rest_api.serializers import RoomHandleSerializer
from voteit.room.rest_api.serializers import RoomSerializer
from voteit.room.rest_api.serializers import SpeakerManagerRoomDetailSerializer
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList


@router.register("rooms", basename="rooms")
class RoomsViewSet(VerboseAutoPermissionViewSetMixin, ModelViewSet):
    serializer_class = RoomSerializer
    filterset_class = ForceMeetingWithRoleFilter
    model = Room
    expected_default_http_status = 400
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "create": None,  # In serializer
        "handle": PERM.HANDLE,
        "handle_speaker": ROOM_PERM_HANDLE_SPEAKER,
        "set_handler": PERM.CHANGE,
        "status": None,
        #  "partial_update": None,  # checked in method - only partial needs to be handled manually
    }

    def get_queryset(self):
        return Room.objects.filter(
            models.Q(meeting__roles__user=self.request.user)
            | models.Q(sls__speakersystemroles__user=self.request.user)
        ).distinct()

    def get_serializer_class(self):
        if self.action == "create":
            return CreateRoomSerializer
        elif self.action in ("partial_update", "retrieve", "update"):
            return RoomDetailSerializer
        return super().get_serializer_class()

    @transaction.atomic(durable=True)
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @transaction.atomic(durable=True)
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(
        methods=["post"],
        detail=True,
        url_path="set-handler",
    )
    def set_handler(self, request, *args, **kwargs):
        room = self.get_object()
        if room.handler != request.user:
            room.handler = request.user
            room.save()
        return Response(data={}, status=200)

    @action(
        methods=["patch"],
        detail=True,
        serializer_class=RoomHandleSerializer,
    )
    def handle(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    @action(
        methods=["patch"],
        detail=True,
        url_path="handle-speaker",
        serializer_class=SpeakerManagerRoomDetailSerializer,
    )
    def handle_speaker(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)

    @action(methods=["get"], detail=True)
    def status(self, request, *args, **kwargs):
        """Preflight check endpoint, to see if it's safe to delete this room."""
        room = self.get_object()
        return Response(
            {
                "speakers": Speaker.objects.filter(speaker_list__room=room).count(),
                "speaker_lists": SpeakerList.objects.filter(room=room).count(),
            }
        )

    def perform_destroy(self, instance):
        with transaction.atomic(durable=True):
            try:
                sls = instance.sls
                sls.delete()
            except ObjectDoesNotExist:
                pass
            instance.delete()
