from django.contrib.auth import get_user_model
from rest_framework import (
    viewsets,
    filters,
)
from rest_framework.permissions import DjangoModelPermissions

from . import serializers


UserModel = get_user_model()


class UserSearchViewSet(viewsets.ModelViewSet):
    model = UserModel
    permission_classes = DjangoModelPermissions,
    queryset = UserModel.objects.all()
    serializer_class = serializers.UserSerializer
    filter_backends = filters.SearchFilter,
    search_fields = 'username', 'email', 'first_name', 'last_name'
