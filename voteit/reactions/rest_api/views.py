from rest_framework.exceptions import ValidationError

from voteit.core.rest_api import router
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.reactions.models import ReactionButton
from voteit.reactions.rest_api import serializers


@router.register("reaction-buttons", basename="reaction-buttons")
class ReactionButtonViewSet(DefaultModelViewSet):
    serializer_class = serializers.ButtonDetailSerializer
    serializer_classes = {
        "create": serializers.ButtonCreateSerializer,
    }
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"
    model = ReactionButton
    queryset = ReactionButton.objects.all()
    filterset_fields = ("meeting",)

    def get_queryset(self):
        if self.detail:
            return self.queryset
        try:
            meeting = self.get_context(self.request)
        except ValidationError:
            meeting = None
        if meeting and self.request.user.has_perm(MeetingPermissions.VIEW, meeting):
            return self.queryset.filter(meeting=meeting)
        return self.queryset.none()
