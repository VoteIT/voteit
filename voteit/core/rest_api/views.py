from django.contrib.auth import get_user_model
from django.contrib.auth import logout
from rest_framework import filters
from rest_framework import serializers
from rest_framework import viewsets
from rest_framework import mixins
from rest_framework import permissions
from rest_framework.decorators import action
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.response import Response

from voteit.core.rest_api.mixins import TransitionsMixin
from voteit.core.rest_api.serializers import UpdateUserSerializer
from voteit.core.rest_api.serializers import UserSerializer

UserModel = get_user_model()


class UserSearchViewSet(viewsets.ModelViewSet):
    model = UserModel
    permission_classes = (DjangoModelPermissions,)
    queryset = UserModel.objects.all()
    serializer_class = UserSerializer
    filter_backends = (filters.SearchFilter,)
    search_fields = "username", "email", "first_name", "last_name"


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
