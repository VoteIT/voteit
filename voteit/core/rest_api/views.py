from django.contrib.auth import get_user_model
from rest_framework import permissions
from rest_framework import (
    viewsets,
    filters,
)
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.viewsets import GenericViewSet
from voteit.core.models import OAuth2Provider
from voteit.core.rest_api.mixins import SerializerClassesMixin

from . import serializers


UserModel = get_user_model()


class UserSearchViewSet(viewsets.ModelViewSet):
    model = UserModel
    permission_classes = (DjangoModelPermissions,)
    queryset = UserModel.objects.all()
    serializer_class = serializers.UserSerializer
    filter_backends = (filters.SearchFilter,)
    search_fields = "username", "email", "first_name", "last_name"


# FIXME Really show all providers...?
class ProviderViewSet(GenericViewSet, SerializerClassesMixin, RetrieveModelMixin):
    permission_classes = [permissions.AllowAny]
    model = OAuth2Provider
    queryset = OAuth2Provider.objects.all()
    serializer_class = serializers.BeginProviderAuthSerializer
    serializer_classes = {"list": serializers.ProviderSerializer}
