import csv

from auditlog.context import disable_auditlog
from django.db import models
from django.db import transaction
from django.db.models import F
from django.db.models import QuerySet
from django.db.models import RestrictedError
from django.http import Http404
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from envelope import INTERNAL
from envelope.app.user_channel.channel import UserChannel
from envelope.channels.messages import RecheckChannelSubscriptions
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

from voteit.core import PERM
from voteit.core.loggers import log_roles_change
from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import StateMachineMixin
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
from voteit.meeting.utils import notify_dialect_changed

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
    StateMachineMixin,
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
            "event": None,  # Permission checked inside SM validators
            "state_machine": None,
        }

    def get_serializer_class(self):
        return self.serializer_classes.get(self.action, self.serializer_class)

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

    @action(methods=["post"], detail=True, url_path="install-dialect")
    def install_dialect(self, request, pk):
        meeting: Meeting = self.get_object()
        if not meeting.is_upcoming:
            # This is an extra check - superusers may bypass permission checks
            raise ValidationError(
                {"dialect": ["Meeting must be upcoming to install dialect."]}
            )
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
        notify_dialect_changed(meeting)
        return Response(status=200)

    @action(methods=["post"], detail=True, url_path="remove-dialect")
    def remove_dialect(self, request, pk):
        meeting: Meeting = self.get_object()
        if not meeting.is_upcoming:
            # This is an extra check - superusers may bypass permission checks
            raise ValidationError(
                {"dialect": ["Meeting must be upcoming to install dialect."]}
            )
        if not meeting.installed_dialect:
            raise ValidationError(
                {"dialect": ["No dialect is installed on this meeting."]}
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic(durable=True):
            handler = dialect_registry.get_merged_handler(meeting.installed_dialect)
            handler.remove(meeting, groups=serializer.validated_data["groups"])
        notify_dialect_changed(meeting)
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
        return MeetingRoles.objects.filter(
            context__participants=self.request.user
        ).prefetch_related("user")

    @action(detail=False, methods=["get"], permission_classes=[])
    def available(self, request):
        return Response(
            [
                role.output().dict(exclude={"predicate_info"})
                for role in MeetingRoles.valid_roles.values()
            ]
        )

    @action(
        detail=False,
        methods=["post"],
        serializer_class=serializers.MeetingChangeRolesSerializer,
        url_path="add",
    )
    @transaction.atomic(durable=True)
    def add_roles(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        meeting = serializer.validated_data["meeting"]
        user = serializer.validated_data["user"]
        if not request.user.has_perm(Meeting.get_perm(PERM.CHANGE_ROLES), meeting):
            raise PermissionDenied
        changed = meeting.add_roles(user, *serializer.validated_data["roles"])
        if changed:
            log_roles_change(
                "Added",
                actor=request.user,
                for_user=user,
                context=meeting,
                roles=changed,
            )
        roles_obj = MeetingRoles.objects.get(context=meeting, user=user)
        return Response(serializers.MeetingRolesSerializer(roles_obj).data)

    @action(
        detail=False,
        methods=["post"],
        serializer_class=serializers.MeetingChangeRolesSerializer,
        url_path="remove",
    )
    @transaction.atomic(durable=True)
    def remove_roles(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        meeting = serializer.validated_data["meeting"]
        user = serializer.validated_data["user"]
        if not request.user.has_perm(Meeting.get_perm(PERM.CHANGE_ROLES), meeting):
            raise PermissionDenied
        changed = meeting.remove_roles(user, *serializer.validated_data["roles"])
        if changed:
            log_roles_change(
                "Removed",
                actor=request.user,
                for_user=user,
                context=meeting,
                roles=changed,
            )
            msg = RecheckChannelSubscriptions(consumer_name="", subscriptions=[])
            UserChannel.from_instance(user, envelope_name=INTERNAL).sync_publish(msg)
        try:
            roles_obj = MeetingRoles.objects.get(context=meeting, user=user)
        except MeetingRoles.DoesNotExist:
            return Response(status=204)
        return Response(serializers.MeetingRolesSerializer(roles_obj).data)


@router.register("meeting-groups", basename="meeting-groups")
class MeetingGroupViewSet(VerboseAutoPermissionViewSetMixin, ModelViewSet):
    serializer_class = serializers.MeetingGroupSerializer
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "create": None,  # In serializer
        "retrieve": None,
        "bulk_create": None,  # Meeting field restricts to moderators
        "bulk_delete": None,  # Meeting field restricts to upcoming + moderators
    }

    def get_serializer_class(self):
        if self.action == "create":
            return serializers.CreateMeetingGroupSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        if self.action == "list":
            return MeetingGroup.objects.none()
        return MeetingGroup.objects.filter(meeting__participants=self.request.user)

    @action(
        methods=["post"],
        detail=False,
        serializer_class=serializers.BulkCreateMeetingGroupsSerializer,
        url_path="bulk-create",
    )
    @transaction.atomic(durable=True)
    def bulk_create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        meeting = serializer.validated_data["meeting"]
        created_count = 0
        updated_count = 0
        for gdata in serializer.validated_data["groups"]:
            _, created = meeting.groups.update_or_create(
                groupid=gdata["groupid"],
                defaults={
                    "title": gdata["title"],
                    "votes": gdata["votes"],
                    "show_on_speaker": gdata["show_on_speaker"],
                    "post_as": gdata["post_as"],
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1
        return Response({"created": created_count, "updated": updated_count})

    @action(
        methods=["post"],
        detail=False,
        serializer_class=serializers.BulkDeleteMeetingGroupsSerializer,
        url_path="bulk-delete",
    )
    @transaction.atomic(durable=True)
    def bulk_delete(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        groups = serializer.validated_data["groups"]
        deleted_count = 0
        restricted = []
        for group in groups:
            try:
                group.delete()
                deleted_count += 1
            except RestrictedError:
                restricted.append(group.title)
        if restricted:
            shown = restricted[:3]
            label = ", ".join(f'"{t}"' for t in shown)
            if len(restricted) > 3:
                label += f" and {len(restricted) - 3} more"
            raise ValidationError(
                {
                    "pks": [
                        f"Meeting group(s) {label} are author of proposals and/or discussion posts or "
                        "have a relation to another group. Clear that first."
                    ]
                }
            )
        return Response({"deleted": deleted_count})

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
