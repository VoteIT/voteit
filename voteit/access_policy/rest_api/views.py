from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpResponseForbidden
from requests_oauthlib import OAuth2Session
from rest_framework import mixins
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from voteit.access_policy.app.policies import AutomaticAccess
from voteit.access_policy.models import MeetingInvite
from voteit.access_policy.permissions import MeetingInvitePermissions

from voteit.access_policy.rest_api import serializers
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.meeting.models import Meeting
from voteit.organisation.schemas import OAuthTokenSchema

if TYPE_CHECKING:
    from voteit.organisation.models import OAuth2Provider


class AccessPoliciesViewSet(viewsets.ReadOnlyModelViewSet):
    model = Meeting
    serializer_class = serializers.MeetingAccessPoliciesSerializer
    permission_classes = (permissions.IsAuthenticated,)

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


class UserMatchedInviteViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = serializers.MeetingInviteSerializer

    def get_token(self):
        # FIXME: Error handling, other persistence???
        data = self.request.session["oauth_token"]
        return OAuthTokenSchema(**data)

    def get_queryset(self):
        if self.action in ("list", "accept", "reject"):
            # FIXME: Error checking etc
            provider: OAuth2Provider = self.request.user.organisation.provider
            token = self.get_token()
            # FIXME: Refresh etc
            auth_session = OAuth2Session(
                client_id=provider.client_id, token=token.dict()
            )
            # FIXME URL
            # Expiring LRU-cache?
            response = auth_session.get(
                "http://localhost:8001/service-api/validated-user-data/"
            )
            if not response.ok:
                response.raise_for_status()
            sdata = {}
            for item in response.json():
                values = sdata.setdefault(item["scope"], set())
                values.add(item["data"])
            return MeetingInvite.objects.find_invites(**sdata)
        elif self.action == "retrieve":
            # Retrieve is permissive in another way - mostly for testing anyway
            return self.request.user.used_invites.all()
        return MeetingInvite.objects.none()

    @action(
        methods=["post"],
        detail=True,
        permission_classes=[permissions.IsAuthenticated],
    )
    def accept(self, request, pk):
        instance: MeetingInvite = self.get_object()
        with transaction.atomic():
            instance.accept(request.user)
            instance.save()
        return Response(status=200, data=self.serializer_class(instance).data)

    @action(
        methods=["post"],
        detail=True,
        permission_classes=[permissions.IsAuthenticated],
    )
    def reject(self, request, pk):
        instance: MeetingInvite = self.get_object()
        with transaction.atomic():
            instance.reject(request.user)
            instance.save()
        return Response(status=200, data=self.serializer_class(instance).data)
