from rest_framework.viewsets import ModelViewSet

from voteit.components.rest_api import serializers
from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import VerboseAutoPermissionViewSetMixin
from voteit.components.models import MeetingComponent

__all__ = ("MeetingComponentViewSet",)


@router.register("meeting-components", basename="meeting-components")
class MeetingComponentViewSet(VerboseAutoPermissionViewSetMixin, ModelViewSet):
    model = MeetingComponent
    serializer_class = serializers.MeetingComponentSerializer
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "create": None,
        "retrieve": None,  # Checked in serializer
    }
    filterset_fields = ("meeting",)

    def get_queryset(self):
        return MeetingComponent.objects.filter(meeting__participants=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return serializers.CreateMeetingComponentSerializer
        elif self.action == "retrieve":
            return serializers.VerboseMeetingComponentSerializer
        return super().get_serializer_class()
