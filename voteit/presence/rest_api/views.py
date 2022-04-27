from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.exceptions import ValidationError

from voteit.core.rest_api import router
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.core.rest_api.base import ReadonlyModelViewSet
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.presence.models import Presence
from voteit.presence.models import PresenceCheck
from voteit.presence.models import PresenceSystem
from voteit.presence.permissions import PresenceCheckPermissions
from voteit.presence.rest_api import serializers


class _MeetingContextViewPerm(DefaultModelViewSet):
    def get_queryset(self):
        if not self.detail:
            try:
                meeting = self.get_context(self.request)
            except ValidationError:
                return self.queryset.none()
            if self.request.user.has_perm(MeetingPermissions.VIEW, meeting):
                return self.queryset.filter(meeting=meeting)
            else:
                return self.queryset.none()
        return self.queryset


@router.register("presence-systems", basename="presence-systems")
class PresenceSystemViewSet(_MeetingContextViewPerm):
    serializer_class = serializers.PresenceSystemDetailSerializer
    serializer_classes = {
        "create": serializers.PresenceSystemCreateSerializer,
    }
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"
    model = PresenceSystem
    queryset = PresenceSystem.objects.all()
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = ("meeting",)


@router.register("presence-checks", basename="presence-checks")
class PresenceCheckViewSet(_MeetingContextViewPerm):
    serializer_class = serializers.PresenceCheckDetailSerializer
    serializer_classes = {"create": serializers.PresenceCheckCreateSerializer}
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"
    model = PresenceCheck
    queryset = PresenceCheck.objects.all()
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = ("meeting",)


@router.register("presences", basename="presences")
class PresenceViewSet(ReadonlyModelViewSet):
    serializer_class = serializers.PresenceDetailSerializer
    context_queryset = PresenceCheck.objects.all()
    context_lookup_kwarg = "presence_check"
    model = Presence
    queryset = Presence.objects.all()
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = ("presence_check",)

    def get_queryset(self):
        if not self.detail:
            try:
                presence_check = self.get_context(self.request)
            except ValidationError:
                return self.queryset.none()
            if self.request.user.has_perm(
                PresenceCheckPermissions.VIEW, presence_check
            ):
                return self.queryset.filter(presence_check=presence_check)
            else:
                return self.queryset.none()
        return self.queryset
