from rest_framework.response import Response

from voteit.meeting.models import Meeting
from voteit.meeting.rest_api.serializers import MeetingDetailSerializer
from voteit.token_api import register_meeting_api
from voteit.token_api.base import MeetingApiBaseViewSet


@register_meeting_api("meeting")
class MeetingView(MeetingApiBaseViewSet):
    token_api_scope = "meeting"
    queryset = Meeting.objects.none()
    serializer_class = MeetingDetailSerializer

    def list(self, request, *args, **kwargs):
        if api_key := getattr(request, "meeting_api_key", None):
            serializer = self.get_serializer(api_key.meeting)
            return Response(serializer.data)
        return Response([])
