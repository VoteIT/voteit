from logging import getLogger
from typing import Dict
from typing import TYPE_CHECKING

from django.db import transaction
from django.http import HttpResponseForbidden
from django.utils.functional import cached_property
from rest_framework import mixins
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.core.rest_api.utils import get_identity_data
from voteit.core.rest_api.permissions import HasIDProxyAPIKey
from voteit.invites.models import MeetingInvite
from voteit.invites.permissions import MeetingInvitePermissions
from voteit.invites.rest_api import serializers
from voteit.meeting.models import Meeting

if TYPE_CHECKING:
    pass

logger = getLogger(__name__)


class MeetingInviteViewSet(DefaultModelViewSet):
    serializer_class = serializers.MeetingInviteSerializer
    serializer_classes = {
        "create": serializers.CreateMeetingInviteSerializer,
    }
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"
    model = MeetingInvite

    def get_queryset(self):
        """
        Generic searches without meeting as part of the query aren't allowed for this view.
        """
        if self.detail:
            # Permission checked against obj
            return MeetingInvite.objects.all()
        else:
            context: Meeting = self.get_context(self.request)
            # This permission can be checked against meetings too
            if not self.request.user.has_perm(MeetingInvitePermissions.VIEW, context):
                return HttpResponseForbidden("You lack the required moderator role")
            return context.invites


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
    def search_data(self) -> Dict:
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


class UsedInvitesViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = serializers.MeetingInviteSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return self.request.user.used_invites.all()


_marker = object()


class HandleMatchedInvitesViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """
    This is for authenticated local users.
    They use this endpoint to accept or reject an invite.
    Note that the data must match returned data from their identity_url
    """

    serializer_class = serializers.MeetingInviteSerializer
    permission_classes = [IsAuthenticated]

    @cached_property
    def identity_data(self) -> Dict:
        return get_identity_data(self.request.user)

    def get_queryset(self):
        # bad request if no user org
        organisation = self.request.user.organisation
        if organisation is None:
            raise ValidationError('Organisation required')
        sdata = {}
        for item in self.identity_data["user_data"]:
            values = sdata.setdefault(item["scope"], set())
            values.add(item["data"])
        return MeetingInvite.objects.find_open_invites(organisation, **sdata)

    def get_matching(self, instance: MeetingInvite):
        for item in self.identity_data["user_data"]:
            if instance.type == item["scope"] and instance.invite_data == item["data"]:
                yield item

    @action(
        methods=["post"],
        detail=True,
    )
    def accept(self, request, pk):
        # Note: Permissions doesn't apply here since it's handled by the queryset
        instance: MeetingInvite = self.get_object()
        matched = list(self.get_matching(instance))
        if not matched:
            # Since queryset has already evaluated this, it shouldn't happen
            raise ValidationError("Couldn't find matching invite")
        with transaction.atomic():
            instance.accept(request.user)
            instance.matched = matched
            instance.save()
        return Response(status=200, data=self.serializer_class(instance).data)

    @action(
        methods=["post"],
        detail=True,
    )
    def reject(self, request, pk):
        # Note: Permissions doesn't apply here since it's handled by the queryset
        instance: MeetingInvite = self.get_object()
        matched = list(self.get_matching(instance))
        if not matched:
            # Since queryset has already evaluated this, it shouldn't happen
            raise ValidationError("Couldn't find matching invite")
        with transaction.atomic():
            instance.reject(request.user)
            instance.matched = matched
            instance.save()
        return Response(status=200, data=self.serializer_class(instance).data)
