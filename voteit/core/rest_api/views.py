from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth import logout
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from rest_framework import mixins
from rest_framework import permissions
from rest_framework import serializers
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import ModelContextMixin
from voteit.core.rest_api.mixins import TransitionsMixin
from voteit.core.rest_api.serializers import UpdateUserSerializer
from voteit.core.rest_api.serializers import UserSerializer
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
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
        if meeting and user.has_perm(MeetingPermissions.MODERATE, meeting):
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
    serializer_class = UserSerializer
    serializer_classes = {
        "logout": serializers.Serializer,
        "update": UpdateUserSerializer,
        "partial_update": UpdateUserSerializer,
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
        logout(request)
        return Response()

    @action(methods=["POST"], detail=True)
    def switch(self, request, pk):
        user = self.get_object()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        serializer = self.serializer_class(user)
        return Response(serializer.data)

    @action(methods=["GET"], detail=False)
    def alternate(self, request):
        if request.user.identity_id:
            qs = self.get_queryset().exclude(pk=request.user.pk)
        else:
            qs = self.User.objects.none()
        serializer = self.serializer_class(qs, many=True)
        return Response(serializer.data)
