from django.db import transaction
from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from voteit.core.rest_api import router
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.meeting import roles
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.models import MeetingRoles
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.rest_api import serializers
from voteit.meeting.rest_api.filters import MeetingRolesFilter
from voteit.organisation.models import Organisation

__all__ = (
    "MeetingViewSet",
    "MeetingRolesViewSet",
    "MeetingGroupViewSet",
)


@router.register("meetings", basename="meeting")
class MeetingViewSet(DefaultModelViewSet):
    model = Meeting
    serializer_class = serializers.MeetingDetailSerializer
    serializer_classes = {
        "list": serializers.MeetingSerializer,
        "set_agenda_order": serializers.AgendaOrderSerializer,
    }
    filter_backends = (
        DjangoFilterBackend,
        SearchFilter,
    )
    search_fields = ("title",)
    filterset_fields = ("public",)
    context_queryset = (
        Organisation.objects.none()
    )  # We've overridden get_context instead

    def get_context(self, request):
        """Override to fetch organisation from the user directly"""
        organisation = request.user.organisation
        if organisation is None:
            raise ValidationError(detail=f"User has no related organisation")
        return organisation

    @property
    def permission_type_map(self):
        data = super().permission_type_map.copy()
        data["set_agenda_order"] = "change"
        return data

    @action(methods=["post"], detail=True)
    def set_agenda_order(self, request, pk):
        serializer = serializers.AgendaOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.validated_data["order"]
        meeting: Meeting = self.get_object()
        agenda_items = meeting.agenda_items.filter(pk__in=order)
        with transaction.atomic():
            for ai in agenda_items:
                ai.order = order.index(ai.pk) + 1
                ai.save()
        return Response(status=201)

    def get_queryset(self) -> QuerySet:
        return Meeting.objects.for_user(self.request.user)

    def perform_create(self, serializer):
        instance: Meeting = serializer.save()
        instance.add_roles(self.request.user, roles.ROLE_MODERATOR)


@router.register("meeting-roles", basename="meeting-roles")
class MeetingRolesViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    model = MeetingRoles
    queryset = MeetingRoles.objects.all()
    serializer_class = serializers.MeetingRolesSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter)
    filterset_class = MeetingRolesFilter
    search_fields = ("^user__userid", "^user__first_name", "^user__last_name")
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        # This is a temp fix to extract meeting PK. Context is still used by the frontend.
        meeting_pk = self.request.query_params.get(
            "meeting", self.request.query_params.get("context", None)
        )
        if meeting_pk is None:
            return self.queryset.none()
        try:
            meeting_pk = int(meeting_pk)
        except (ValueError, TypeError):
            raise ValidationError({"meeting": ["Must be a number"]})
        meeting = Meeting.objects.filter(pk=meeting_pk).first()
        if meeting is None:
            raise ValidationError({"meeting": ["No such meeting"]})
        # FIXME: Public meeting is used in an odd way in frontend. This needs to be cleaned up.
        # Related to #206
        if not meeting.has_any_roles(self.request.user, "participant", "moderator"):
            raise PermissionDenied()
        return self.queryset.filter(context=meeting).prefetch_related("user")


@router.register("meeting-groups", basename="meeting-groups")
class MeetingGroupViewSet(DefaultModelViewSet):
    model = MeetingGroup
    serializer_class = serializers.MeetingGroupSerializer
    context_lookup_kwarg: str = "meeting"

    @property
    def context_queryset(self) -> QuerySet:
        return Meeting.objects.for_user(self.request.user)

    def get_queryset(self):
        if self.detail:
            # Permission checked against object
            return MeetingGroup.objects.all()
        try:
            meeting = self.get_context(self.request)
        except ValidationError:
            meeting = None
        if meeting and self.request.user.has_perm(MeetingPermissions.VIEW, meeting):
            return MeetingGroup.objects.filter(meeting=meeting)
        return MeetingGroup.objects.none()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
