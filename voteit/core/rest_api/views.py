from django.contrib.auth import get_user_model, logout
from rest_framework import filters
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.response import Response
from voteit.core.rest_api.mixins import SerializerClassesMixin
from voteit.core.rest_api.mixins import TransitionsMixin

from . import serializers

UserModel = get_user_model()


class UserSearchViewSet(viewsets.ModelViewSet):
    model = UserModel
    permission_classes = (DjangoModelPermissions,)
    queryset = UserModel.objects.all()
    serializer_class = serializers.UserSerializer
    filter_backends = (filters.SearchFilter,)
    search_fields = "username", "email", "first_name", "last_name"


class UserView(TransitionsMixin, viewsets.GenericViewSet):
    """A single view to get data for currently logged in user."""

    serializer_class = serializers.UserSerializer
    serializer_classes = {"logout": serializers.serializers.Serializer}

    def list(self, request):
        serializer = self.serializer_class(request.user)
        return Response(serializer.data)

    @action(methods=["POST"], detail=False)
    def logout(self, request):
        logout(request)
        return Response("You have been logged out")
