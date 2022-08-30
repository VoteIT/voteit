from django.utils.translation import gettext as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from voteit.core.rest_api import router
from voteit.core.rest_api.base import DefaultModelViewSet
from voteit.core.rest_api.mixins import AutoPermissionViewSetMixin
from voteit.core.rest_api.mixins import SerializerClassesMixin
from voteit.core.rest_api.permissions import HasIDProxyAPIKey
from voteit.organisation.models import Organisation
from voteit.organisation.models import OrganisationRoles
from voteit.organisation.models import TermsOfService
from voteit.organisation.models import UserConsent
from voteit.organisation.permissions import OrgPermissions
from voteit.organisation.rest_api import serializers
from voteit.organisation.rest_api.filters import UserPkFilter


@router.register("organisations", basename="organisations")
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
    expected_default_http_status = 401
    # TODO: Not decided how to host multiple organisations. For now, always return a list of one.
    def get_queryset(self):
        # Host is forced for authenticated too
        host = self.request.get_host()
        hostname = host.split(":")[0]
        if self.request.user.is_authenticated and self.request.user.organisation:
            if hostname != self.request.user.organisation.host:
                raise AuthenticationFailed(
                    detail=_("You're logged in to another organisation")
                )
            return self.queryset.filter(
                pk=self.request.user.organisation.pk, host=hostname
            )
        return self.queryset.filter(host=hostname)

    def list(self, request, *args, **kwargs):
        """
        A list that may contain one item, but no more.
        """
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data)


@router.register("id-organisations", basename="id-organisations")
class IDProxyOrganisationViewSet(
    SerializerClassesMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    serializer_class = serializers.IDOrganisationSerializer
    serializer_classes = {
        "create": serializers.IDOrganisationUpdateSerializer,
        "update": serializers.IDOrganisationUpdateSerializer,
        "partial_update": serializers.IDOrganisationUpdateSerializer,
    }
    permission_classes = (HasIDProxyAPIKey,)
    model = Organisation
    queryset = Organisation.objects.all()
    expected_default_http_status = 401


@router.register("tos", basename="tos")
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


@router.register("user_consents", basename="user_consents")
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


@router.register("organisation-roles")
class OrganisationRolesViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    model = OrganisationRoles
    queryset = OrganisationRoles.objects.all()
    serializer_class = serializers.OrganisationRolesSerializer
    filter_backends = (
        DjangoFilterBackend,
        SearchFilter,
    )
    filterset_class = UserPkFilter
    search_fields = (
        "^user__first_name",
        "^user__last_name",
    )
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        user = self.request.user
        if user.has_perm(OrgPermissions.VIEW_ROLES, user.organisation):
            return self.queryset.filter(context=user.organisation)
        return self.queryset.none()
