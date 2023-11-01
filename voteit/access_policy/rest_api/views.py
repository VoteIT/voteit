from logging import getLogger

from django.db import transaction
from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from voteit.access_policy.app.policies import AutomaticAccess
from voteit.access_policy.rest_api import serializers
from voteit.core.rest_api import router
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions

logger = getLogger(__name__)


@router.register("access-policies", basename="access-policies")
class AccessPoliciesViewSet(viewsets.ReadOnlyModelViewSet):
    model = Meeting
    serializer_class = serializers.MeetingAccessPoliciesSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self) -> QuerySet:
        return Meeting.objects.for_user(self.request.user)


@router.register("access-policy-automatic", basename="access-policy-automatic")
class AutomaticAccessViewSet(DefaultModelViewSet):
    model = AutomaticAccess
    serializer_class = serializers.AutomaticAccessSerializer
    serializer_classes = {"create": serializers.CreateAutomaticAccessSerializer}
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"
    permission_classes = (IsAuthenticated,)
    queryset = AutomaticAccess.objects.all()

    @property
    def permission_type_map(self) -> dict:
        return {"join": None, **super().permission_type_map}

    def get_queryset(self) -> QuerySet:
        if self.action == "list":
            try:
                meeting: Meeting = self.get_context(self.request)
            except ValidationError:
                meeting = None
            if meeting and self.request.user.has_perm(
                MeetingPermissions.MODERATE, meeting
            ):
                return self.queryset.filter(meeting=meeting)
            else:
                return self.queryset.none()
        return self.queryset

    @action(detail=True, methods=["post"])
    def join(self, request: Request, **kw):
        """
        Allow a user to join a meeting if it has active AutomaticAccess policy.
        """
        aa: AutomaticAccess = self.get_object()
        if not aa.active:
            raise ValidationError("Not enabled")
        with transaction.atomic(durable=True):
            aa.assign(request.user)
        return Response(status=204)
