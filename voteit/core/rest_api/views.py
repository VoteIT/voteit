from django.contrib.auth import get_user_model
from rest_framework import filters
from rest_framework import mixins
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.permissions import DjangoModelPermissions
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


# FIXME Really show all providers...? Force filtering via org?
class ProviderViewSet(
    SerializerClassesMixin,
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    permission_classes = [permissions.AllowAny]
    model = OAuth2Provider
    queryset = OAuth2Provider.objects.all()
    serializer_class = serializers.BeginProviderAuthSerializer
    serializer_classes = {"list": serializers.ProviderSerializer}
    # lookup_field = "provider_id"
