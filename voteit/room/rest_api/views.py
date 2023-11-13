from django.db import transaction

from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from voteit.core.rest_api import router
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.room.models import Room
from voteit.room.rest_api.serializers import CreateRoomSerializer
from voteit.room.rest_api.serializers import RoomDetailSerializer
from voteit.room.rest_api.serializers import RoomHandleSerializer
from voteit.room.rest_api.serializers import RoomSerializer


@router.register("rooms", basename="rooms")
class RoomsViewSet(DefaultModelViewSet):
    serializer_class = RoomSerializer
    serializer_classes = {
        "create": CreateRoomSerializer,
        "update": RoomDetailSerializer,
        "partial_update": RoomDetailSerializer,
    }
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"
    queryset = Room.objects.all()
    model = Room

    @property
    def permission_type_map(self) -> dict:
        return {
            "set_handler": "change",
            "handle": "handle",
            **super().permission_type_map,
        }

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
        methods=["patch", "put"],
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
    @transaction.atomic(durable=True)
    def handle(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @transaction.atomic(durable=True)
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
