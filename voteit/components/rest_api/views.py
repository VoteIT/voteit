from django.db.models import QuerySet
from rest_framework.exceptions import ValidationError

from voteit.components.rest_api import serializers
from voteit.core.rest_api import router
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.meeting.models import Meeting
from voteit.components.models import MeetingComponent
from voteit.meeting.permissions import MeetingPermissions

__all__ = ("MeetingComponentViewSet",)


@router.register("meeting-components", basename="meeting-components")
class MeetingComponentViewSet(DefaultModelViewSet):
    model = MeetingComponent
    serializer_class = serializers.MeetingComponentSerializer
    serializer_classes = {
        "create": serializers.CreateMeetingComponentSerializer,
        "retrieve": serializers.VerboseMeetingComponentSerializer,
    }
    context_lookup_kwarg: str = "meeting"

    @property
    def context_queryset(self) -> QuerySet:
        return Meeting.objects.for_user(self.request.user)

    def get_queryset(self):
        if self.detail:
            # Permission checked against object
            return MeetingComponent.objects.all()
        try:
            meeting = self.get_context(self.request)
        except ValidationError:
            meeting = None
        if meeting and self.request.user.has_perm(MeetingPermissions.VIEW, meeting):
            return MeetingComponent.objects.filter(meeting=meeting)
        return MeetingComponent.objects.none()
