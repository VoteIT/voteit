from rest_framework import mixins

from voteit.invites.models import MeetingInvite
from voteit.invites.rest_api.serializers import InviteCreateSerializer
from voteit.invites.rest_api.serializers import MeetingInviteSerializer
from voteit.token_api import register_meeting_api
from voteit.token_api.base import MeetingApiBaseViewSet


class InviteCreateViaTokenSerializer(InviteCreateSerializer):
    meeting = None  # removed from input; injected from API key in validate()

    def validate(self, attrs):
        attrs["meeting"] = self.context["request"].meeting_api_key.meeting
        return super().validate(attrs)


@register_meeting_api("invites")
class InvitesView(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    MeetingApiBaseViewSet,
):
    token_api_scope = "invites"
    serializer_class = MeetingInviteSerializer

    def get_queryset(self):
        if api_key := getattr(self.request, "meeting_api_key", None):
            return MeetingInvite.objects.filter(meeting_id=api_key.meeting_id)
        return MeetingInvite.objects.none()

    def get_serializer_class(self):
        if self.action == "create":
            return InviteCreateViaTokenSerializer
        return super().get_serializer_class()
