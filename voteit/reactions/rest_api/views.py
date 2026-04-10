from rest_framework.viewsets import ModelViewSet

from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import VerboseAutoPermissionViewSetMixin
from voteit.meeting.rest_api.filters import ForceMeetingWithRoleFilter
from voteit.reactions.models import ReactionButton
from voteit.reactions.rest_api import serializers


@router.register("reaction-buttons", basename="reaction-buttons")
class ReactionButtonViewSet(VerboseAutoPermissionViewSetMixin, ModelViewSet):
    serializer_class = serializers.ButtonDetailSerializer
    filterset_class = ForceMeetingWithRoleFilter
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "create": None,  # In serializer
        "retrieve": None,
    }
    expected_default_http_status = 400

    def get_serializer_class(self):
        if self.action == "create":
            return serializers.ButtonCreateSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        return ReactionButton.objects.filter(meeting__participants=self.request.user)
