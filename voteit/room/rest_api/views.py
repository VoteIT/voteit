from contextlib import suppress

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from voteit.core.rest_api import router
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.core.rest_api.serializers import ForceDeleteSerializer
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.room.models import Room
from voteit.room.permissions import RoomPermissions
from voteit.room.rest_api.serializers import CreateRoomSerializer
from voteit.room.rest_api.serializers import RoomDetailSerializer
from voteit.room.rest_api.serializers import RoomHandleSerializer
from voteit.room.rest_api.serializers import RoomSerializer
from voteit.room.rest_api.serializers import SpeakerManagerRoomDetailSerializer
from voteit.speaker.permissions import SpeakerSystemPermissions


@router.register("rooms", basename="rooms")
class RoomsViewSet(DefaultModelViewSet):
    serializer_class = RoomSerializer
    serializer_classes = {
        "create": CreateRoomSerializer,
        "update": RoomDetailSerializer,
        "partial_update": RoomDetailSerializer,
        "destroy": ForceDeleteSerializer,
    }
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"
    queryset = Room.objects.all()
    model = Room

    @property
    def permission_type_map(self) -> dict:
        default = super().permission_type_map.copy()
        default.update(
            {
                "set_handler": "change",
                "handle": "handle",
                "partial_update": None,  # checked in method - only partial needs to be handled manually
            }
        )
        return default

    def get_queryset(self):
        if self.action == "list":
            try:
                meeting = self.get_context(self.request)
            except ValidationError:
                meeting = None
            if meeting and self.request.user.has_perm(MeetingPermissions.VIEW, meeting):
                return self.queryset.filter(meeting=meeting)
            return self.queryset.none()
        return self.queryset

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
    @transaction.atomic(durable=True)
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
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @transaction.atomic(durable=True)
    def destroy(self, request, *args, **kwargs):
        instance: Room = self.get_object()
        try:
            sls = instance.sls
        except ObjectDoesNotExist:
            sls = None
        if sls is not None:
            from voteit.speaker.models import Speaker

            if scount := Speaker.objects.filter(
                speaker_list__speaker_system=sls
            ).count():
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                if not serializer.data["force"]:
                    raise ValidationError(
                        {
                            "force": [
                                f"Room contains {scount} speaker items which would be deleted, "
                                f"set force=true to delete"
                            ]
                        }
                    )
            instance.sls.delete()
        return super().destroy(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.action != "partial_update":
            return super().get_serializer_class()
        room = self.get_object()
        if self.request.user.has_perm(RoomPermissions.CHANGE, room):
            return super().get_serializer_class()
        # FIXME Empty==object not found?
        else:
            with suppress(ObjectDoesNotExist):  # sls is a reverse relation
                if room.sls is not None and self.request.user.has_perm(
                    SpeakerSystemPermissions.MANAGE, room.sls
                ):
                    return SpeakerManagerRoomDetailSerializer
        raise PermissionDenied()
