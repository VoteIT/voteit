from contextlib import suppress
from logging import getLogger
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils.functional import cached_property
from rest_framework import mixins
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from voteit.core.rest_api import router
from voteit.core.rest_api.base import TransitionsMixin
from voteit.core.rest_api.mixins import AutoPermissionViewSetMixin
from voteit.core.rest_api.utils import get_identity_data
from voteit.core.rest_api.permissions import HasIDProxyAPIKey
from voteit.invites.models import MeetingInvite
from voteit.invites.rest_api import serializers
from voteit.invites.schemas import InviteDataTypesSchema
from voteit.invites.utils import get_invite_adapter_registry
from voteit.meeting.models import Meeting

if TYPE_CHECKING:
    pass

logger = getLogger(__name__)


@router.register("meeting-invites", basename="meeting-invites")
class MeetingInviteViewSet(
    AutoPermissionViewSetMixin,
    TransitionsMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"
    model = MeetingInvite
    permission_type_map = {
        **AutoPermissionViewSetMixin.permission_type_map,
        "bulk_delete": None,
        "bulk_revoke": None,
    }

    def get_queryset(self):
        """
        Generic searches without meeting as part of the query aren't allowed for this view.
        """
        if self.detail:
            # Permission checked against obj
            return MeetingInvite.objects.all()
        return MeetingInvite.objects.none()

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

    @transaction.atomic(durable=True)
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

    expected_default_http_status = 403
    serializer_class = serializers.ExternalMeetingInviteSerializer
    permission_classes = [IsAuthenticated]

    @cached_property
    def identity_data(self) -> dict:
        return get_identity_data(self.request.user)

    def get_queryset(self):
        # bad request if no user org
        organisation = self.request.user.organisation
        if organisation is None:
            raise ValidationError("Organisation required")
        sdata = {}
        for item in self.identity_data["user_data"]:
            values = sdata.setdefault(item["scope"], set())
            values.add(item["data"])
        return MeetingInvite.objects.find_open_invites(
            organisation=organisation, **sdata
        )

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
