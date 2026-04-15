from logging import getLogger

from django.db import transaction
from django.db.models import QuerySet
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework.viewsets import ReadOnlyModelViewSet

from voteit.access_policy.app.policies import AutomaticAccess
from voteit.access_policy.rest_api import serializers
from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import VerboseAutoPermissionViewSetMixin
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR

logger = getLogger(__name__)


@router.register("access-policies", basename="access-policies")
class AccessPoliciesViewSet(ReadOnlyModelViewSet):
    model = Meeting
    serializer_class = serializers.MeetingAccessPoliciesSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self) -> QuerySet:
        return Meeting.objects.for_user(self.request.user)


@router.register("access-policy-automatic", basename="access-policy-automatic")
class AutomaticAccessViewSet(VerboseAutoPermissionViewSetMixin, ModelViewSet):
    serializer_class = serializers.AutomaticAccessSerializer
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "join": None,
        "retrieve": None,
        "create": None,  # Checked in serializer
    }

    def get_serializer_class(self):
        if self.action == "create":
            return serializers.CreateAutomaticAccessSerializer
        return super().get_serializer_class()

    def get_queryset(self) -> QuerySet:
        if self.action in ("list", "join"):
            return AutomaticAccess.objects.filter(
                meeting__organisation_id=self.request.user.organisation_id
            )
        return AutomaticAccess.objects.filter(
            meeting__roles__user=self.request.user,
            meeting__roles__assigned__contains=ROLE_MODERATOR,
        )

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
