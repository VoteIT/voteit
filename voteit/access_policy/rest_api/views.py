from rest_framework import permissions, viewsets

from voteit.access_policy.rest_api.serializers import (
    MeetingAccessPoliciesSerializer,
)
from voteit.meeting.models import Meeting


class AccessPoliciesViewSet(viewsets.ReadOnlyModelViewSet):

    model = Meeting
    queryset = Meeting.objects.all()
    serializer_class = MeetingAccessPoliciesSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        # FIXME: Testing and permissions
        if self.request.user.is_superuser:
            return self.queryset
        return []
