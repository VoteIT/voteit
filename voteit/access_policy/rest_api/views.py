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

from voteit.access_policy.app.policies import AutomaticAccess
from voteit.access_policy.models import MeetingInvite
from voteit.access_policy.permissions import MeetingInvitePermissions
from voteit.access_policy.rest_api import serializers
from voteit.access_policy.rest_api.authentication import InviteBasicAuthentication
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.meeting.models import Meeting
from voteit.organisation.schemas import OAuthTokenSchema

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

    ## FIXME post from service with profile id and make sure that user exists
    # Error message to suggest registration
    # Clean up the other views!!!


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

    def get_queryset(self):
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
        return MeetingInvite.objects.find_invites(**search_data)


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

    def get_token(self):
        # FIXME: Error handling, other persistence???
        data = self.request.session["oauth_token"]
        return OAuthTokenSchema(**data)

    @cached_property
    def identity_data(self) -> Dict:
        # FIXME: Error checking etc
        provider: OAuth2Provider = self.request.user.organisation.provider
        token = self.get_token()
        # FIXME: Refresh etc
        auth_session = OAuth2Session(client_id=provider.client_id, token=token.dict())
        # Expiring LRU-cache?
        response = auth_session.get(provider.identity_url)
        if not response.ok:
            response.raise_for_status()
        return response.json()

    def get_queryset(self):
        sdata = {}
        for item in self.identity_data["identity"]:
            values = sdata.setdefault(item["scope"], set())
            values.add(item["data"])
        return MeetingInvite.objects.find_invites(**sdata)

    def get_matching(self, instance: MeetingInvite):
        for item in self.identity_data["identity"]:
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
