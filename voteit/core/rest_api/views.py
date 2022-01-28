from django.contrib.auth import get_user_model
from django.contrib.auth import logout
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from rest_framework import serializers
from rest_framework import viewsets
from rest_framework import mixins
from rest_framework import permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from voteit.core.rest_api.mixins import ModelContextMixin

from voteit.core.rest_api.mixins import TransitionsMixin
from voteit.core.rest_api.serializers import UpdateUserSerializer
from voteit.core.rest_api.serializers import UserSerializer
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.organisation.permissions import OrgPermissions

UserModel = get_user_model()


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
        meeting = self.get_context(self.request)
        if user.has_perm(MeetingPermissions.MODERATE, meeting):
            return meeting.participants.all()
        return UserModel.objects.none()


class UserView(TransitionsMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """A single view to get data for currently logged in user."""

    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = UserSerializer
    serializer_classes = {
        "logout": serializers.Serializer,
        "update": UpdateUserSerializer,
    }

    def get_queryset(self):
        User = UserSerializer.Meta.model
        if self.request.user.pk:
            return User.objects.filter(pk=self.request.user.pk)
        return User.objects.none()

    def list(self, request):
        serializer = self.serializer_class(request.user)
        return Response(serializer.data)

    @action(methods=["POST"], detail=False)
    def logout(self, request):
        logout(request)
        return Response()
