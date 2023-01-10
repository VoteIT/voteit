import csv
from contextlib import suppress

from django.db import transaction
from django.db.models import QuerySet
from django.db.models import F
from django.http import Http404
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from voteit.core.decorators import has_perm_drf
from voteit.core.rest_api import router
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.core.rest_api.serializers import PydanticFieldSerializer
from voteit.meeting import roles
from voteit.meeting.models import GroupMembership
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.models import MeetingRoles
from voteit.meeting.permissions import MeetingGroupPermissions
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.rest_api import serializers
from voteit.meeting.rest_api.filters import MeetingRolesFilter
from voteit.meeting.utils import get_named_path_dict
from voteit.meeting.utils import load_dialect_file
from voteit.organisation.models import Organisation

__all__ = (
    "MeetingViewSet",
    "MeetingRolesViewSet",
    "MeetingGroupViewSet",
    "GroupMembershipViewSet",
    "ExportParticipantsViewSet",
)


@router.register("meetings", basename="meeting")
class MeetingViewSet(DefaultModelViewSet):
    model = Meeting
    serializer_class = serializers.MeetingDetailSerializer
    serializer_classes = {
        "create": serializers.CreateMeetingSerializer,
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
        # FIXME: We need to prefetch or annotate user roles here to avoid N+1-problem.
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


@router.register("group-memberships", basename="group-memberships")
class GroupMembershipViewSet(DefaultModelViewSet):
    model = GroupMembership
    serializer_class = serializers.GroupMembershipSerializer
    serializer_classes = {"create": serializers.CreateGroupMembershipSerializer}
    context_lookup_kwarg: str = "meeting_group"

    @property
    def context_queryset(self) -> QuerySet:
        return MeetingGroup.objects.filter(
            meeting__in=Meeting.objects.for_user(self.request.user)
        )

    def get_queryset(self):
        if self.detail:
            # Permission checked against object
            return GroupMembership.objects.all()
        try:
            meeting_group = self.get_context(self.request)
        except ValidationError:
            meeting_group = None
        if meeting_group and self.request.user.has_perm(
            MeetingGroupPermissions.VIEW, meeting_group
        ):
            return GroupMembership.objects.filter(meeting_group=meeting_group)
        return GroupMembership.objects.none()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


@router.register("export-participants", basename="export-participants")
class ExportParticipantsViewSet(viewsets.GenericViewSet):
    model = Meeting
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self) -> QuerySet:
        return Meeting.objects.for_user(self.request.user)

    def list(self, request):
        return Response()

    def get_export_qs(self, meeting):
        return meeting.roles.all().annotate(
            first_name=F("user__first_name"),
            last_name=F("user__last_name"),
            email=F("user__email"),
            userid=F("user__userid"),
        )

    @action(
        methods=["get"],
        detail=True,
        serializer_class=serializers.ParticipantExportSerializer,
    )
    @has_perm_drf(MeetingPermissions.MODERATE)
    def csv(self, request, *args, **kwargs):
        meeting = self.get_object()
        serializer = self.get_serializer(self.get_export_qs(meeting), many=True)
        if not serializer.data:
            raise Http404("No data yet")
        response = HttpResponse(content_type="text/csv")
        response[
            "Content-Disposition"
        ] = f'attachment; filename="participants_m{meeting.pk}_export.csv"'
        writer = csv.DictWriter(response, fieldnames=serializer.child.fields)
        writer.writeheader()
        for row in serializer.data:
            writer.writerow(row)
        return response

    @action(
        methods=["get"],
        detail=True,
        serializer_class=serializers.ParticipantExportSerializer,
        renderer_classes=[JSONRenderer],
    )
    @has_perm_drf(MeetingPermissions.MODERATE)
    def json(self, request, *args, **kwargs):
        meeting = self.get_object()
        serializer = self.get_serializer(self.get_export_qs(meeting), many=True)
        return Response(
            serializer.data,
            headers={
                "Content-Disposition": f'attachment; filename="participants_m{meeting.pk}_export.json"'
            },
        )


@router.register("meeting-dialects", basename="meeting-dialects")
class MeetingDialectsViewSet(viewsets.ViewSet):
    """
    Endpoint for installable meeting dialects
    """

    def list(self, request, *args, **kwargs):
        result = []
        for name, path in get_named_path_dict().items():
            with suppress(TypeError, ValueError):
                handler = load_dialect_file(name, path)
                result.append(handler.data.dict(exclude_none=True))
        result.sort(key=lambda x: x["name"])
        return Response(data=result)
