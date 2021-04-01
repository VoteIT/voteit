from rest_framework import mixins
from rest_framework import permissions
from rest_framework.viewsets import GenericViewSet
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

    # FIXME: We'll allow access to all organisations right now. This might change
    # def get_queryset(self):
    #     if self.request.user.is_superuser:
    #         return self.queryset
    #     if self.request.user.organisation:
    #         return self.queryset.filter(pk=self.request.user.organisation.pk)
    #     return self.queryset.none()


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


# FIXME Really show all providers...? Force filtering via org?
# class ProviderViewSet(
#     SerializerClassesMixin,
#     viewsets.GenericViewSet,
#     mixins.ListModelMixin,
#     mixins.RetrieveModelMixin,
# ):
#     permission_classes = [permissions.AllowAny]
#     model = OAuth2Provider
#     queryset = OAuth2Provider.objects.all()
#     serializer_class = serializers.BeginProviderAuthSerializer
#     serializer_classes = {"list": serializers.ProviderSerializer}
#     # lookup_field = "provider_id"
