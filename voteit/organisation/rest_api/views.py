from django.utils.translation import gettext as _
from rest_framework import mixins
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.exceptions import AuthenticationFailed

from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.core.rest_api.mixins import AutoPermissionViewSetMixin
from voteit.organisation.models import Organisation
from voteit.organisation.models import TermsOfService
from voteit.organisation.models import UserConsent
from voteit.organisation.rest_api import serializers


class OrganisationViewSet(
    AutoPermissionViewSetMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    model = Organisation
    queryset = Organisation.objects.all()
    serializer_class = serializers.OrganisationSerializer

    def get_subdomain(self) -> str:
        host = self.request.get_host()
        return host.split(":")[0].split(".")[0]

    # TODO: Not decided how to host multiple organisations. For now, always return a list of one.
    def get_queryset(self):
        # Subdomain is forced for authenticated too
        if self.request.user.is_authenticated and self.request.user.organisation:
            subdomain = self.get_subdomain()
            if subdomain != self.request.user.organisation.subdomain:
                raise AuthenticationFailed(
                    detail=_("You're logged in to another organisation")
                )
            return self.queryset.filter(
                pk=self.request.user.organisation.pk, subdomain=subdomain
            )
        return self.queryset.filter(subdomain=self.get_subdomain())

    def list(self, request, *args, **kwargs):
        """
        A list that may contain one item, but no more.
        """
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data)


class TOSViewSet(DefaultModelViewSet):
    serializer_class = serializers.TOSSerializer
    serializer_classes = {"create": serializers.TOSCreateSerializer}
    context_queryset = Organisation.objects.all()
    context_lookup_kwarg = "organisation"
    model = TermsOfService

    def get_queryset(self):
        if self.request.user.is_superuser:
            return self.model.objects.all()
        if self.request.user.organisation:
            return self.model.objects.filter(
                organisation=self.request.user.organisation
            )
        return self.model.objects.none()


class UserConsentViewSet(DefaultModelViewSet):
    serializer_class = serializers.UserConsentSerializer
    serializer_classes = {"create": serializers.UserConsentCreateSerializer}
    context_queryset = TermsOfService.objects.all()
    context_lookup_kwarg = "tos"
    model = UserConsent

    def get_queryset(self):
        if self.request.user.is_superuser:
            return self.model.objects.all()
        if self.request.user.organisation:
            return self.model.objects.filter(
                tos__organisation=self.request.user.organisation
            )
        return self.model.objects.none()
