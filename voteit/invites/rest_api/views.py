from contextlib import suppress
from itertools import groupby
from logging import getLogger

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from rest_framework import mixins
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import TransitionsMixin
from voteit.core.rest_api.mixins import VerboseAutoPermissionViewSetMixin
from voteit.core.rest_api.permissions import HasIDProxyAPIKey
from voteit.invites.models import MeetingInvite
from voteit.invites.rest_api import serializers
from voteit.invites.schemas import InviteDataTypesSchema
from voteit.invites.schemas import InvitesResultSchema
from voteit.invites.utils import get_invite_adapter_registry
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.workflows import MeetingWf
from voteit.organisation.utils import get_idproxy_user_data


logger = getLogger(__name__)


@router.register("meeting-invites", basename="meeting-invites")
class MeetingInviteViewSet(
    VerboseAutoPermissionViewSetMixin,
    TransitionsMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    filterset_fields = ("meeting",)
    permission_type_map = {
        **VerboseAutoPermissionViewSetMixin.permission_type_map,
        "retrieve": None,
        "create": None,
        "bulk_delete": None,
        "bulk_revoke": None,
        "import_invites": None,
    }

    def get_queryset(self):
        """
        Generic searches without meeting as part of the query aren't allowed for this view.
        """
        return MeetingInvite.objects.filter(
            meeting__roles__user=self.request.user,
            meeting__roles__assigned__contains=ROLE_MODERATOR,
        ).exclude(state__in=MeetingWf.archived_states)

    def retrieve(self, request, *args, **kwargs):
        """
        Returns a list of any annotation data related to a specific invite.
        """
        instance = self.get_object()
        reg = get_invite_adapter_registry()
        data = {"pk": instance.pk}
        annotations = data["annotations"] = []
        for adapter in reg.values():
            if adapter.is_annotation:
                adapted = adapter(instance)
                for adata in adapted.get_annotations():
                    annotations.append({"name": adapter.name, **adata})
        return Response(data)

    def list(self, *args, **kwargs):
        return Response([])

    def create(self, request, *args, **kwargs):
        serializer = serializers.InviteCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(
            {"added": result.added, "changed": result.changed, "existed": result.existed},
            status=201,
        )

    @action(
        methods=["post"],
        detail=False,
        serializer_class=serializers.InviteBulkSerializer,
        url_path="bulk-delete",
    )
    def bulk_delete(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invites: list[int] = serializer.validated_data["invites"]
        with transaction.atomic(durable=True):
            count = MeetingInvite.objects.filter(id__in=invites).delete()[0]
        return Response({"deleted": count})

    @transaction.atomic(durable=True)
    @action(
        methods=["post"],
        detail=False,
        serializer_class=serializers.InviteBulkSerializer,
        url_path="bulk-revoke",
    )
    def bulk_revoke(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invites: list[int] = serializer.validated_data["invites"]
        qs = MeetingInvite.objects.filter(id__in=invites)
        count = qs.count()
        for invite in qs:
            invite.revoke()
            invite.save()
        return Response({"revoked": count})

    @action(
        methods=["post"],
        detail=False,
        url_path="import",
        parser_classes=[MultiPartParser],
        serializer_class=serializers.InviteImportSerializer,
    )
    def import_invites(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        meeting = vd["meeting"]
        columns: list[str] = vd["columns"]
        rows: list[list[str]] = vd["rows"]
        roles_per_row: list[list[str]] = vd["roles_per_row"]
        dryrun: bool = vd["dryrun"]

        reg = get_invite_adapter_registry()
        invite_result = InvitesResultSchema()
        annotation_results = []

        with transaction.atomic(durable=True):
            # Group rows by unique role combination and create invites per group
            indexed = sorted(enumerate(rows), key=lambda t: roles_per_row[t[0]])
            for role_combo, group_iter in groupby(
                indexed, key=lambda t: roles_per_row[t[0]]
            ):
                group_rows = [row for _, row in group_iter]
                items = list(reg.build_ud_query_seq(columns, group_rows))
                if not items:
                    continue

                # Moderator lockout protection
                if ROLE_MODERATOR not in role_combo:
                    existing_qs, _conflicting = meeting.invites.find_mixed_user_data(
                        *items
                    )
                    curr_moderators = meeting.roles.filter(
                        assigned__contains=ROLE_MODERATOR
                    ).values_list("user", flat=True)
                    at_risk = existing_qs.filter(used_by__in=curr_moderators)
                    if at_risk.exists():
                        userids = ", ".join(
                            x
                            for x in at_risk.values_list("used_by__userid", flat=True)
                            if x
                        )
                        raise ValidationError(
                            _(
                                "Your action would downgrade permissions for some moderators. "
                                "Handle moderators via participants tab instead. "
                                "Related to userID(s): %(userids)s"
                            )
                            % {"userids": userids}
                        )

                result = meeting.invites.create_or_update_mixed(
                    data=items, roles=role_combo, meeting=meeting
                )
                invite_result.added += result.added
                invite_result.changed += result.changed
                invite_result.existed += result.existed

            # Run annotations if annotation columns are present
            if reg.get_annotations(columns):
                try:
                    reg.run_validators(columns=columns, rows=rows, meeting=meeting)
                except ValueError as exc:
                    raise ValidationError(str(exc))
                invites_qs = meeting.invites.all()
                for ann_result in reg.run_annotations(
                    columns=columns,
                    rows=rows,
                    invites_qs=invites_qs,
                    meeting=meeting,
                ):
                    if ann_result:
                        annotation_results.append(
                            {
                                "name": ann_result.name,
                                "added": ann_result.added,
                                "changed": ann_result.changed,
                                "existed": ann_result.existed,
                            }
                        )

            if dryrun:
                transaction.set_rollback(True)

        return Response(
            {
                "invites": invite_result.dict(),
                "annotations": annotation_results,
                "dryrun": dryrun,
            }
        )


@router.register("match-invites", basename="match-invites")
class MatchInvitesViewSet(viewsets.GenericViewSet):
    """
    This view is meant as a service endpoint for matching identity data.

    It uses basic http auth with username and password to match the user.
    This should be a user without any access at all, and it must be listed within settings as:
    INVITE_SERVICE_USERS = ["username", ...]
    Settings must contain the service users
    """

    serializer_class = serializers.ExternalMeetingInviteSerializer
    permission_classes = (HasIDProxyAPIKey,)

    @action(
        methods=["post"],
        detail=False,
    )
    def query(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data)

    @cached_property
    def search_data(self) -> dict:
        many = isinstance(self.request.data, list)
        serializer = serializers.InviteQuerySerializer(
            data=self.request.data, many=many
        )
        # FIXME: Decide when a validation goes sour
        serializer.is_valid(raise_exception=True)
        search_data = {}
        for item in serializer.to_internal_value(serializer.data):
            values = search_data.setdefault(item["scope"], set())
            values.add(item["data"])
        return search_data

    def get_queryset(self):
        return MeetingInvite.objects.find_open_invites(**self.search_data)

    @action(
        methods=["post"],
        detail=True,
    )
    def reject(self, request, pk):
        # Note: Permissions doesn't apply here since it's handled by the queryset
        instance: MeetingInvite = self.get_object()
        with transaction.atomic():
            instance.reject(request.user)
            instance.save()
        return Response(status=200, data=self.serializer_class(instance).data)


_marker = object()


@router.register("handle-matched-invites", basename="handle-matched-invites")
class HandleMatchedInvitesViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """
    This is for authenticated local users.
    They use this endpoint to accept or reject an invite.
    Note that the data must match returned data from their identity_url
    """

    serializer_class = serializers.ExternalMeetingInviteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        organisation = self.request.user.organisation
        if organisation is None:
            raise ValidationError("Organisation required")
        if matched := get_idproxy_user_data(self.request.user):
            return MeetingInvite.objects.find_open_invites(
                organisation=organisation, **matched
            )
        return MeetingInvite.objects.none()

    @action(
        methods=["post"],
        detail=True,
    )
    def accept(self, request, pk):
        # Note: Permissions doesn't apply here since it's handled by the queryset
        instance: MeetingInvite = self.get_object()
        with transaction.atomic():
            instance.accept(request.user)
            instance.save()
        return Response(status=200, data=self.serializer_class(instance).data)

    @action(
        methods=["post"],
        detail=True,
    )
    def reject(self, request, pk):
        # Note: Permissions doesn't apply here since it's handled by the queryset
        instance: MeetingInvite = self.get_object()
        with transaction.atomic():
            instance.reject(request.user)
            instance.save()
        return Response(status=200, data=self.serializer_class(instance).data)


@router.register("invite-data-types", basename="invite-data-types")
class InviteDataTypesViewSet(ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        scopes = ["email"]
        with suppress(ObjectDoesNotExist, AttributeError):
            scope = request.user.organisation.provider.scope
            scopes = scope.split()
        reg = get_invite_adapter_registry()
        results = []
        for v in reg.values():
            if v.is_user_data and v.name not in scopes:
                continue
            data = InviteDataTypesSchema.from_orm(v)
            results.append(data.dict())
        return Response(data=results)
