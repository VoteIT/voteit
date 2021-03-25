from rest_framework import permissions
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.viewsets import GenericViewSet
from voteit.organisation.models import Organisation
from voteit.organisation.rest_api import serializers


class OrganisationViewSet(GenericViewSet, RetrieveModelMixin):
    permission_classes = [permissions.AllowAny]
    model = Organisation
    queryset = Organisation.objects.all()
    serializer_class = serializers.OrganisationSerializer
