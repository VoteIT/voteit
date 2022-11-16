from contextlib import suppress

from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth import logout
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from rest_framework import mixins
from rest_framework import permissions
from rest_framework import serializers
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from voteit.core.loggers import log_auth
from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import ModelContextMixin
from voteit.core.rest_api.mixins import TransitionsMixin
from voteit.core.rest_api.serializers import UserAndRolesSerializer
from voteit.core.rest_api.serializers import UserSerializer
from voteit.core.rest_api.utils import get_identity_data
from voteit.meeting.models import Meeting
from voteit.organisation.permissions import OrgPermissions

UserModel = get_user_model()


@router.register("users", "users")
class UserSearchViewSet(ModelContextMixin, viewsets.ReadOnlyModelViewSet):
    model = UserModel
    permission_classes = (
        permissions.IsAuthenticated,
    )  # Permissions checked in queryset!
    serializer_class = UserSerializer
    filter_backends = (
        DjangoFilterBackend,
        filters.SearchFilter,
    )
    filterset_fields = ("meeting",)
    search_fields = "username", "email", "first_name", "last_name"
    context_queryset = Meeting.objects.all()
    context_lookup_kwarg = "meeting"

    def get_queryset(self):
        """
        User search as follows:
        - superuser: all (basically only during development)
        - org managers: organisation members
        - moderators: all meeting participants
        """
        user = self.request.user
        if user.is_superuser or user.has_perm(OrgPermissions.MANAGE, user.organisation):
            return user.organisation.users.all()
        # Method will raise 404 if meeting doesn't exist
        try:
            meeting = self.get_context(self.request)
        except ValidationError:
            meeting = None
        # FIXME: Public meeting is used in an odd way in frontend. This needs to be cleaned up.
        if meeting and meeting.has_roles(user, "participant"):
            return meeting.participants.all()
        return UserModel.objects.none()


@router.register("user", basename="user")
class UserView(
    TransitionsMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    A single view to get data for currently logged in user.
    """

    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = UserAndRolesSerializer
    serializer_classes = {
        "logout": serializers.Serializer,
    }

    @property
    def User(self):
        return UserSerializer.Meta.model

    def get_queryset(self):
        if self.request.user.pk:
            if self.request.user.identity_id:
                return self.User.objects.filter(
                    identity_id=self.request.user.identity_id, is_active=True
                )
            # Only for manually created users, i.e. in dev environment
            return self.User.objects.filter(pk=self.request.user.pk)
        return self.User.objects.none()

    def list(self, request):
        serializer = self.serializer_class(request.user)
        return Response(serializer.data)

    @action(methods=["POST"], detail=False)
    def logout(self, request):
        log_auth("Logout", request=request)
        logout(request)
        return Response()

    @action(methods=["POST"], detail=True)
    @transaction.atomic
    def switch(self, request, pk):
        user = self.get_object()
        inherit_oauth = True
        with suppress(PermissionDenied):
            user.oauth_session()
            inherit_oauth = False
        if inherit_oauth:
            if curr_token := request.user.access_tokens.order_by("expires_at").first():
                # We don't really know what to do if it doesn't exist, and we don't have to care
                # since it won't happen when logged in via oauth
                user.access_tokens.create(
                    expires_at=curr_token.expires_at,
                    expires_in=curr_token.expires_in,
                    provider=curr_token.provider,
                    access_token=curr_token.access_token,
                    refresh_token=curr_token.refresh_token,
                )
        log_auth("Switch user", for_user=user, request=request)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        serializer = self.get_serializer(user)
        return Response(serializer.data)

    @action(methods=["GET"], detail=False)
    def alternate(self, request):
        if request.user.identity_id:
            qs = self.get_queryset().exclude(pk=request.user.pk)
        else:
            qs = self.User.objects.none()
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(methods=["GET"], detail=False)
    def email_choices(self, request):
        identity_data = get_identity_data(request.user)
        valid_emails = {
            x["data"] for x in identity_data["user_data"] if x["scope"] == "email"
        }
        return Response(data={"emails": sorted(valid_emails)})


@router.register("health", basename="health")
class HealthCheckView(GenericViewSet):
    permission_classes = [permissions.AllowAny]

    def list(self, request):
        return Response("OK!")
