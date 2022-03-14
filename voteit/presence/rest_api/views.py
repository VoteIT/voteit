from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.meeting.models import Meeting
from voteit.presence.models import PresenceSystem, PresenceCheck

from . import serializers
from ...core.rest_api import router
from ...meeting.permissions import MeetingPermissions


@router.register("presence-systems", basename="presence-systems")
class PresenceSystemViewSet(DefaultModelViewSet):
    serializer_class = serializers.PresenceSystemDetailSerializer
    serializer_classes = {
        "create": serializers.PresenceSystemCreateSerializer,
    }
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"
    model = PresenceSystem
    queryset = PresenceSystem.objects.all()

    def get_queryset(self):
        if self.action == "list":
            meeting = self.get_context(self.request)
            if self.request.user.has_perm(MeetingPermissions.VIEW, meeting):
                return self.queryset.filter(meeting=meeting)
            else:
                return self.queryset.none()
        return self.queryset


@router.register("presence-checks", basename="presence-checks")
class PresenceCheckViewSet(DefaultModelViewSet):
    serializer_class = serializers.PresenceCheckDetailSerializer
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"
    model = PresenceCheck
    queryset = PresenceCheck.objects.all()

    def get_queryset(self):
        if self.action == "list":
            meeting = self.get_context(self.request)
            if self.request.user.has_perm(MeetingPermissions.VIEW, meeting):
                return self.queryset.filter(meeting=meeting)
            else:
                return self.queryset.none()
        return self.queryset
