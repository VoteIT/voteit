from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpResponseForbidden
from django.utils.functional import cached_property
from requests_oauthlib import OAuth2Session
from rest_framework import mixins
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from typing import Dict

from rest_framework.serializers import Serializer
from voteit.access_policy.app.policies import AutomaticAccess
from voteit.access_policy.models import MeetingInvite
from voteit.access_policy.permissions import MeetingInvitePermissions
from voteit.access_policy.rest_api import serializers
from voteit.access_policy.rest_api.authentication import InviteBasicAuthentication
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.meeting.models import Meeting

if TYPE_CHECKING:
    from voteit.organisation.models import OAuth2Provider


class AccessPoliciesViewSet(viewsets.ReadOnlyModelViewSet):
    model = Meeting
    serializer_class = serializers.MeetingAccessPoliciesSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self) -> QuerySet:
        return Meeting.objects.for_user(self.request.user)

    @action(detail=True, methods=["post"])
    def join(self, request: Request, **kw):
        """Allow a user to join a meeting if it has active AutomaticAccess policy."""
        meeting: Meeting = self.get_object()
        if meeting.participants.filter(pk=request.user.pk).exists():
            return Response(
                status=204
            )  # Already participant, respond positively immediately
        try:
            automatic = AutomaticAccess.objects.get(active=True, meeting=meeting)
        except ObjectDoesNotExist:
            return Response({"msg": "Not allowed"}, status=400)

        automatic.assign(request.user)
        return Response(status=204)


class MeetingInviteViewSet(DefaultModelViewSet):
    serializer_class = serializers.MeetingInviteSerializer
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

    serializer_class = serializers.MeetingInviteSerializer
    authentication_classes = (InviteBasicAuthentication,)
    permission_classes = (IsAuthenticated,)

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
        return MeetingInvite.objects.find_invites(**self.search_data)

    @action(
        methods=["post"],
        detail=True,
    )
    def reject(self, request, pk):
        # Note: Permissions doesn't apply here since it's handled by the queryset
        instance: MeetingInvite = self.get_object()
        matched = []
        for scope, data_items in self.search_data.items():
            invite_data = instance.data.get(scope, _marker)
            if invite_data == _marker:
                continue
            for data in data_items:
                if invite_data == data:
                    matched.append({scope: data})
        with transaction.atomic():
            instance.reject(request.user)
            instance.matched = matched
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
        # FIXME: Error checking etc
        provider: OAuth2Provider = self.request.user.organisation.provider
        oauth_session = self.request.user.oauth_session()
        response = oauth_session.get(provider.identity_url)
        if not response.ok:
            # FIXME: Wrong exception for this context
            response.raise_for_status()
        return response.json()

    def get_queryset(self):
        sdata = {}
        for item in self.identity_data["user_data"]:
            values = sdata.setdefault(item["scope"], set())
            values.add(item["data"])
        return MeetingInvite.objects.find_invites(**sdata)

    def get_matching(self, instance: MeetingInvite):
        for item in self.identity_data["user_data"]:
            if instance.data.get(item["scope"], _marker) == item["data"]:
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
