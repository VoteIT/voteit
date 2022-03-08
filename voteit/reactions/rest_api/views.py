from django_filters.rest_framework import DjangoFilterBackend
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.reactions.models import ReactionButton
from voteit.reactions.rest_api import serializers


class ReactionButtonViewSet(DefaultModelViewSet):
    serializer_class = serializers.ButtonDetailSerializer
    serializer_classes = {
        "create": serializers.ButtonCreateSerializer,
    }
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"
    model = ReactionButton
    queryset = ReactionButton.objects.all()
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = ("meeting",)

    def get_queryset(self):
        if self.action == "list":
            meeting = self.get_context(self.request)
            if self.request.user.has_perm(MeetingPermissions.VIEW, meeting):
                return self.queryset.filter(meeting=meeting)
            return self.queryset.none()
        return self.queryset
