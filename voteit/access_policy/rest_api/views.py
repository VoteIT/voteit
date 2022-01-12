from logging import getLogger

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from voteit.access_policy.app.policies import AutomaticAccess
from voteit.access_policy.rest_api import serializers
from voteit.meeting.models import Meeting

logger = getLogger(__name__)


class AccessPoliciesViewSet(viewsets.ReadOnlyModelViewSet):
    model = Meeting
    serializer_class = serializers.MeetingAccessPoliciesSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self) -> QuerySet:
        return Meeting.objects.for_user(self.request.user)

    @action(detail=True, methods=["post"])
    def join(self, request: Request, **kw):
        """Allow a user to join a meeting if it has active AutomaticAccess policy."""
        meeting: Meeting = self.get_object()
        if meeting.participants.filter(pk=request.user.pk).exists():
            return Response(
                status=204
            )  # Already participant, respond positively immediately
        try:
            automatic = AutomaticAccess.objects.get(active=True, meeting=meeting)
        except ObjectDoesNotExist:
            return Response({"msg": "Not allowed"}, status=400)

        automatic.assign(request.user)
        return Response(status=204)
