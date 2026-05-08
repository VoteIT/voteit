import csv

from auditlog.context import disable_auditlog
from django.db import models
from django.db import transaction
from django.db.models import QuerySet
from django.db.models import F
from django.db.models import RestrictedError
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
from rest_framework.viewsets import ModelViewSet

from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import TransitionsMixin
from voteit.core.rest_api.mixins import VerboseAutoPermissionViewSetMixin
from voteit.meeting import PERM_CHANGE_DIALECT
from voteit.meeting.dialects import dialect_registry
from voteit.meeting.models import GroupMembership
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingGroup
from voteit.meeting.models import MeetingRoles
from voteit.meeting.rest_api import serializers
from voteit.meeting.rest_api.filters import MeetingRolesFilter
from voteit.meeting.roles import ROLE_MODERATOR

__all__ = (
    "MeetingViewSet",
    "MeetingRolesViewSet",
    "MeetingGroupViewSet",
    "GroupMembershipViewSet",
    "ExportParticipantsViewSet",
)


@router.register("meetings", basename="meeting")
class MeetingViewSet(
    VerboseAutoPermissionViewSetMixin,
    TransitionsMixin,
    viewsets.ModelViewSet,
):
    model = Meeting
    serializer_class = serializers.MeetingDetailSerializer
    serializer_classes = {
        "create": serializers.CreateMeetingSerializer,
        "list": serializers.MeetingSerializer,
        "set_agenda_order": serializers.AgendaOrderSerializer,
        "install_dialect": serializers.InstallDialectSerializer,
        "remove_dialect": serializers.RemoveDialectSerializer,
    }
    filter_backends = (
        DjangoFilterBackend,
        SearchFilter,
    )
    search_fields = ("title",)
    filterset_fields = ("public",)

    @property
    def permission_type_map(self):
        return {
            **super().permission_type_map,
            "set_agenda_order": "change",
            "install_dialect": PERM_CHANGE_DIALECT,
            "remove_dialect": PERM_CHANGE_DIALECT,
            "retrieve": None,  # Handled by queryset
            "transitions": None,  # Checked in transitions
        }

    @action(methods=["post"], detail=True)
    def set_agenda_order(self, request, pk):
        serializer = serializers.AgendaOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.validated_data["order"]
        meeting: Meeting = self.get_object()
        agenda_items = meeting.agenda_items.filter(pk__in=order)
        with transaction.atomic():
            with (
                disable_auditlog()
            ):  # Will load every object once again otherwise, and we don't log order.
                for ai in agenda_items:
                    ai.order = order.index(ai.pk) + 1
                    ai.save()
        return Response(status=201)

    @action(methods=["post"], detail=True)
    def install_dialect(self, request, pk):
        meeting: Meeting = self.get_object()
        if meeting.installed_dialect:
            raise ValidationError(
                {"dialect": ["A dialect is already installed. Remove it first."]}
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic(durable=True):
            handler = dialect_registry.get_merged_handler(
                serializer.validated_data["dialect"]
            )
            handler.install(meeting)
        return Response(status=200)

    @action(methods=["post"], detail=True)
    def remove_dialect(self, request, pk):
        meeting: Meeting = self.get_object()
        if not meeting.installed_dialect:
            raise ValidationError(
                {"dialect": ["No dialect is installed on this meeting."]}
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic(durable=True):
            handler = dialect_registry.get_merged_handler(meeting.installed_dialect)
            handler.remove(meeting, groups=serializer.validated_data["groups"])
        return Response(status=200)

    def get_queryset(self) -> QuerySet:
        qs = Meeting.objects.for_user(self.request.user)
        meeting_roles_q = MeetingRoles.objects.filter(
            context_id=models.OuterRef("pk"),
            user=self.request.user,
        ).values("assigned")
        qs = qs.annotate(user_roles=models.Subquery(meeting_roles_q))
        return qs

    # Note: Create already has an atomic block within the serializer
    @transaction.atomic(durable=True)
    def update(self, *args, **kwargs):
        return super().update(*args, **kwargs)


@router.register("meeting-roles", basename="meeting-roles")
class MeetingRolesViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
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
            return MeetingRoles.objects.none()
        try:
            meeting_pk = int(meeting_pk)
        except (ValueError, TypeError):
            raise ValidationError({"meeting": ["Must be a number"]})
        return MeetingRoles.objects.filter(
            context__participants=self.request.user, context_id=meeting_pk
        ).prefetch_related("user")


@router.register("meeting-groups", basename="meeting-groups")
class MeetingGroupViewSet(VerboseAutoPermissionViewSetMixin, ModelViewSet):
    serializer_class = serializers.MeetingGroupSerializer
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "create": None,  # In serializer
        "retrieve": None,
    }

    def get_serializer_class(self):
        if self.action == "create":
            return serializers.CreateMeetingGroupSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        if self.action == "list":
            return MeetingGroup.objects.none()
        return MeetingGroup.objects.filter(meeting__participants=self.request.user)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except RestrictedError as exc:
            raise PermissionDenied(
                "Meeting group is author of proposals and/or discussion posts or "
                "has a relation to another group. Clear that first."
            ) from exc


@router.register("group-memberships", basename="group-memberships")
class GroupMembershipViewSet(VerboseAutoPermissionViewSetMixin, ModelViewSet):
    serializer_class = serializers.GroupMembershipSerializer
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "create": None,  # In serializer
        "retrieve": None,
    }

    def get_serializer_class(self):
        if self.action == "create":
            return serializers.CreateGroupMembershipSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        if self.action == "list":
            return GroupMembership.objects.none()
        return GroupMembership.objects.filter(
            meeting_group__meeting__participants=self.request.user
        )

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        # Role-signal will be delegated, see signals.py
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer: serializers.GroupMembershipSerializer):
        # if serializer.instance.role is None:
        role_added = None
        role_removed = None
        serializer.instance: GroupMembership
        if "role" in serializer.validated_data:
            role_added = (
                serializer.validated_data["role"] and serializer.instance.role is None
            )
            role_removed = (
                not serializer.validated_data["role"] and serializer.instance.role
            )
        serializer.save()
        if role_added:
            serializer.instance.signal_role_added()
        if role_removed:
            serializer.instance.signal_role_removed(role=role_removed)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        # Role-signal will be delegated, see signals.py
        return super().destroy(request, *args, **kwargs)


@router.register("export-participants", basename="export-participants")
class ExportParticipantsViewSet(viewsets.GenericViewSet):
    def get_queryset(self) -> QuerySet:
        return Meeting.objects.filter(
            roles__user=self.request.user, roles__assigned__contains=ROLE_MODERATOR
        )

    def list(self, request):
        return Response(data=[])

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
    def csv(self, request, *args, **kwargs):
        meeting = self.get_object()
        serializer = self.get_serializer(self.get_export_qs(meeting), many=True)
        if not serializer.data:
            raise Http404("No data yet")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="participants_m{meeting.pk}_export.csv"'
        )
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
    def json(self, request, *args, **kwargs):
        meeting = self.get_object()
        serializer = self.get_serializer(self.get_export_qs(meeting), many=True)
        return Response(
            serializer.data,
            headers={
                "Content-Disposition": f'attachment; filename="participants_m{meeting.pk}_export.json"'
            },
        )


@router.register("export-meeting-groups", basename="export-meeting-groups")
class ExportMeetingGroupsViewSet(viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self) -> QuerySet:
        return Meeting.objects.filter(
            roles__user=self.request.user, roles__assigned__contains=ROLE_MODERATOR
        )

    def list(self, request):  # To avoid errors
        return Response(data=[])

    @action(
        methods=["get"],
        detail=True,
        serializer_class=serializers.MeetingGroupExportSerializer,
    )
    def csv(self, request, *args, **kwargs):
        meeting = self.get_object()
        serializer = self.get_serializer(meeting.groups.all(), many=True)
        if not serializer.data:
            raise Http404("No data yet")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="meting_groups_m{meeting.pk}_export.csv"'
        )
        writer = csv.DictWriter(response, fieldnames=serializer.child.fields)
        writer.writeheader()
        for row in serializer.data:
            writer.writerow(row)
        return response

    @action(
        methods=["get"],
        detail=True,
        serializer_class=serializers.MeetingGroupExportSerializer,
        renderer_classes=[JSONRenderer],
    )
    def json(self, request, *args, **kwargs):
        meeting = self.get_object()
        serializer = self.get_serializer(meeting.groups.all(), many=True)
        return Response(
            serializer.data,
            headers={
                "Content-Disposition": f'attachment; filename="meting_groups_m{meeting.pk}_export.json"'
            },
        )


@router.register("meeting-dialects", basename="meeting-dialects")
class MeetingDialectsViewSet(viewsets.ViewSet):
    """
    Endpoint for installable meeting dialects
    """

    permission_classes = [permissions.IsAuthenticated]

    def list(self, request, *args, **kwargs):
        org_installable = dialect_registry.get_org_installable(
            organisation=request.user.organisation
        )
        return Response(
            data=sorted(org_installable.values(), key=lambda item: item.get("name"))
        )
