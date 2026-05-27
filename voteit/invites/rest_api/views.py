from contextlib import suppress
from itertools import groupby
from logging import getLogger

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils.functional import cached_property
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
    """
    Moderator-facing endpoint for managing meeting invites.

    Invite state is pushed over WebSocket (MeetingInvitesChannel); the list
    action intentionally returns [] — do not poll this endpoint for invite lists.
    """

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
        GET /api/meeting-invites/{pk}/

        Returns annotation data attached to a single invite.

        Response:
            {
                "pk": 42,
                "annotations": [
                    {"name": "group", "meeting_group": 7, "role": null}
                ]
            }

        Returns 404 if the invite does not belong to a meeting the user moderates.
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
        """
        GET /api/meeting-invites/

        Always returns []. Invite state is delivered over WebSocket on
        MeetingInvitesChannel subscription, not via polling.
        """
        return Response([])

    def create(self, request, *args, **kwargs):
        """
        POST /api/meeting-invites/

        Create or update invites from a JSON list. Each item is a flat dict
        mixing identity fields (e.g. email) and optional annotation fields
        (e.g. group, grouprole). All items share the same roles.

        Request:
            {
                "meeting": 1,
                "roles": ["pa"],
                "data": [
                    {"email": "alice@example.com", "group": "board"},
                    {"email": "bob@example.com"}
                ],
                "dryrun": false
            }

        - Identity fields are validated and normalised via their adapter schema.
        - Annotation fields are normalised via preflight (strip, lowercase).
        - grouprole requires group to be present in the same item, and the meeting dialect must use grouproles.
        - An item must have at least one identity field.
        - Existing invites with matching identity data have their roles updated.
        - Raises 400 if the new roles would downgrade an existing moderator.

        Response 201:
            {
                "invites": {"added": 1, "changed": 0, "existed": 1},
                "annotations": [{"name": "group", "added": 1, "changed": 0, "existed": 0}],
                "dryrun": false
            }

        With dryrun: true the transaction is rolled back and no data is written.
        """
        serializer = serializers.InviteCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.save(), status=201)

    @action(
        methods=["post"],
        detail=False,
        serializer_class=serializers.InviteBulkSerializer,
        url_path="bulk-delete",
    )
    def bulk_delete(self, request, *args, **kwargs):
        """
        POST /api/meeting-invites/bulk-delete/

        Permanently delete a list of invites. All PKs must belong to the
        specified meeting, which the requesting user must moderate.

        Request:
            {"meeting": 1, "invites": [10, 11, 12]}

        Response:
            {"deleted": 3}
        """
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
        """
        POST /api/meeting-invites/bulk-revoke/

        Transition a list of open invites to the 'revoked' state. All PKs must
        belong to the specified meeting, which the requesting user must moderate.
        Already-revoked or accepted invites are included in the count but the
        FSM transition will raise if not applicable — filter to open invites
        on the client if needed.

        Request:
            {"meeting": 1, "invites": [10, 11]}

        Response:
            {"revoked": 2}
        """
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
        """
        POST /api/meeting-invites/import/   (multipart/form-data)

        Create or update invites from an uploaded spreadsheet or text file.
        File format is detected by content, not filename:
          - XLSX (.xlsx) — Excel 2007+
          - ODS (.ods) — LibreOffice / Google Sheets
          - CSV / TSV — UTF-8 plain text, separator auto-detected
          - Headerless email list — single column without a header row

        The first row must be column headers. Recognised columns:
          - Identity: email, swedish_ssn (org-dependent)
          - Annotation: group, grouprole
          - roles — per-row role override; omit to default all rows to PARTICIPANT

        Example TSV:
            email           group     roles
            alice@x.com     board     pa,mo
            bob@x.com       board

        Form fields:
            meeting  — meeting PK (integer)
            file     — the spreadsheet file
            dryrun   — "true" to validate without writing (optional, default false)

        Rows with the same role combination are grouped and processed together.
        Rows with annotation columns (group, grouprole) are annotated after
        invites are created.

        Response:
            {
                "invites": {"added": 2, "changed": 0, "existed": 1},
                "annotations": [{"name": "group", "added": 2, "changed": 0, "existed": 1}],
                "dryrun": false
            }

        Raises 400 if:
          - File exceeds 2 MB or 1000 data rows
          - Column names are unrecognised or violate cross-column constraints
          - Any group IDs in the file don't exist in the meeting
          - The new roles would downgrade an existing moderator
        """
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

                serializers._raise_if_moderator_lockout(meeting, items, role_combo)
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
    Service endpoint for the external ID-proxy login system.

    Auth: API key via HTTP_API_KEY header (setting: ID_PROXY_API_KEY).
    This endpoint is called by the identity provider during login to look up
    pending invites for a user before they have a local account.
    """

    serializer_class = serializers.ExternalMeetingInviteSerializer
    permission_classes = (HasIDProxyAPIKey,)

    @action(
        methods=["post"],
        detail=False,
    )
    def query(self, request):
        """
        POST /api/match-invites/query/

        Find all open invites matching one or more identity scope+value pairs.
        The request body is a list of validated identity assertions from the
        ID-proxy provider.

        Request:
            [
                {"scope": "email", "data": "alice@example.com", "validated": "2024-01-15T10:00:00Z"},
                {"scope": "swedish_ssn", "data": "191212121212", "validated": "2024-01-15T10:00:00Z"}
            ]

        Response — list of matching open invites:
            [
                {
                    "pk": 42,
                    "user_data": {"email": "alice@example.com"},
                    "roles": ["pa"],
                    "state": "open",
                    "meeting": 1,
                    "meeting_title": "Annual general meeting",
                    "organisation_host": "org.example.com",
                    "created": "2024-01-10T08:00:00Z",
                    "modified": "2024-01-10T08:00:00Z",
                    "used_by": null,
                    "used_at": null
                }
            ]

        Returns [] if no open invites match. Scopes not present in the registry
        are silently ignored (logged as warnings) to avoid breaking login flows
        when scope lists diverge between systems.
        """
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
        """
        POST /api/match-invites/{pk}/reject/

        Reject a specific invite on behalf of the user. The queryset is scoped
        to invites matching the request's identity data, so this returns 404 if
        the invite PK does not match the caller's identity — no explicit
        permission check is needed.

        Request body: same identity list as /query/ (used for queryset scoping).

        Response 200: the updated invite object (state: "rejected").
        """
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
    Authenticated local user endpoint for accepting or rejecting their own invites.

    The user must belong to an
    organisation and have identity data stored via their ID-proxy social auth.
    The queryset is scoped to open invites that match the user's own identity —
    no explicit object-level permission check is performed.
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
        """
        POST /api/handle-matched-invites/{pk}/accept/

        Accept an invite. Grants the invite's roles to the user and applies
        any pending group annotations (MeetingGroupAnnotation rows). Returns
        404 if the invite does not match the user's own identity data.

        Response 200: the updated invite object (state: "accepted").
        """
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
        """
        POST /api/handle-matched-invites/{pk}/reject/

        Reject an invite. The invite moves to 'rejected' state and is recorded
        as used by this user. Returns 404 if the invite does not match the
        user's own identity data.

        Response 200: the updated invite object (state: "rejected").
        """
        # Note: Permissions doesn't apply here since it's handled by the queryset
        instance: MeetingInvite = self.get_object()
        with transaction.atomic():
            instance.reject(request.user)
            instance.save()
        return Response(status=200, data=self.serializer_class(instance).data)


@router.register("invite-data-types", basename="invite-data-types")
class InviteDataTypesViewSet(ViewSet):
    """
    Lists the registered invite adapter types available to the requesting user's
    organisation. Used by the frontend to know which identity and annotation
    fields to offer when building invite forms.
    """

    permission_classes = [IsAuthenticated]

    def list(self, request):
        """
        GET /api/invite-data-types/

        Returns all registered adapter types filtered by the organisation's
        provider scope. If the user has no organisation or provider, only
        the 'email' adapter is returned.

        Response:
            [
                {
                    "name": "email",
                    "title": "Email",
                    "is_user_data": true,
                    "is_annotation": false,
                    "is_clearable": false,
                    "is_runnable": true
                },
                {
                    "name": "group",
                    "title": "GroupID",
                    "is_user_data": false,
                    "is_annotation": true,
                    "is_clearable": true,
                    "is_runnable": true
                }
            ]
        """
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
