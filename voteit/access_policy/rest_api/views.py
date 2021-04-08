from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet
from requests_oauthlib import OAuth2Session
from rest_framework import mixins
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from voteit.access_policy.app.policies import AutomaticAccess
from voteit.access_policy.models import MeetingInvite

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
    queryset = MeetingInvite.objects.all()
    model = MeetingInvite


class UserMatchedInviteViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = serializers.MeetingInviteSerializer

    def get_queryset(self):
        # FIXME: Error checking etc
        data = self.request.session["oauth_token"]
        token = OAuthTokenSchema(**data)
        provider: OAuth2Provider = self.request.user.organisation.provider
        # FIXME: Refresh etc
        auth_session = OAuth2Session(client_id=provider.client_id, token=token.dict())
        # FIXME URL
        # Expiring LRU-cache?
        response = auth_session.get(
            "http://localhost:8001/service-api/validated-user-data/"
        )
        if not response.ok:
            response.raise_for_status()
        sdata = {}
        for item in response.json():
            # FIXME {'pk': 1, 'identities': [1], 'id': 1, 'user': 1, 'validated': '2021-03-25T10:36:59Z', 'data': {'email': 'admin@betahaus.net'}, 'scope': 'email'},
            for (k, v) in item["data"].items():
                values = sdata.setdefault(k, set())
                values.add(v)
        return MeetingInvite.objects.find_invites(**sdata)

        # identity_response = auth_session.get(provider.identity_url)
