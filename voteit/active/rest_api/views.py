from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from voteit.active.components import ActiveUsersComponent
from voteit.active.models import ActiveUser
from voteit.active.rest_api.serializers import ActiveUserSerializer
from voteit.active.rest_api.serializers import PurgeInactiveUsersSerializer
from voteit.active.utils import get_inactive_qs
from voteit.core import PERM
from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import VerboseAutoPermissionViewSetMixin
from voteit.core.workflows import EnabledWf
from voteit.meeting.models import Meeting


@router.register("active-users", basename="active-users")
class ActiveUserViewSet(VerboseAutoPermissionViewSetMixin, GenericViewSet):
    serializer_class = ActiveUserSerializer
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "active": None,
        "purge": PERM.CHANGE,
    }

    def get_queryset(self):
        return Meeting.objects.filter(
            participants=self.request.user,
            components__component_name=ActiveUsersComponent.name,
            components__state=EnabledWf.ON,
        )

    def list(self, request, *args, **kwargs):
        return Response([])

    def retrieve(self, request, *args, **kwargs):
        meeting = self.get_object()
        return Response(data={"title": meeting.title, "id": meeting.id})

    @action(
        detail=True,
        methods=["post"],
    )
    def active(self, request, **kwargs):
        meeting = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["active"]:
            _, created = ActiveUser.objects.get_or_create(
                meeting=meeting, user=request.user
            )
            return Response(
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
            )
        else:
            ActiveUser.objects.filter(meeting=meeting, user=request.user).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=["post"],
        serializer_class=PurgeInactiveUsersSerializer,
    )
    def purge(self, request, pk=None):
        meeting = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        older_active = get_inactive_qs(
            meeting, hours=serializer.validated_data["hours"]
        )
        count, _ = older_active.delete()
        return Response(data={"count": count}, status=status.HTTP_200_OK)
