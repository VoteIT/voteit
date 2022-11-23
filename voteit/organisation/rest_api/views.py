from __future__ import annotations
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework import exceptions
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from voteit.core.loggers import notification_logger
from voteit.core.rest_api import router
from voteit.core.rest_api.mixins import AutoPermissionViewSetMixin
from voteit.core.rest_api.mixins import SerializerClassesMixin
from voteit.core.rest_api.permissions import HasIDProxyAPIKey
from voteit.organisation.models import Organisation
from voteit.organisation.models import OrganisationRoles
from voteit.organisation.permissions import OrgPermissions
from voteit.organisation.rest_api import serializers
from voteit.organisation.rest_api.filters import OrphanUserEmailFilter
from voteit.organisation.rest_api.filters import UserIdentitiesFilter
from voteit.organisation.rest_api.filters import UserPkFilter

if TYPE_CHECKING:
    from voteit.core.models import User as UserType


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
                raise exceptions.AuthenticationFailed(
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


# @router.register("tos", basename="tos")
# class TOSViewSet(DefaultModelViewSet):
#     serializer_class = serializers.TOSSerializer
#     serializer_classes = {"create": serializers.TOSCreateSerializer}
#     context_queryset = Organisation.objects.all()
#     context_lookup_kwarg = "organisation"
#     model = TermsOfService
#
#     def get_queryset(self):
#         if self.request.user.is_superuser:
#             return self.model.objects.all()
#         if self.request.user.organisation:
#             return self.model.objects.filter(
#                 organisation=self.request.user.organisation
#             )
#         return self.model.objects.none()


# @router.register("user_consents", basename="user_consents")
# class UserConsentViewSet(DefaultModelViewSet):
#     serializer_class = serializers.UserConsentSerializer
#     serializer_classes = {"create": serializers.UserConsentCreateSerializer}
#     context_queryset = TermsOfService.objects.all()
#     context_lookup_kwarg = "tos"
#     model = UserConsent
#
#     def get_queryset(self):
#         if self.request.user.is_superuser:
#             return self.model.objects.all()
#         if self.request.user.organisation:
#             return self.model.objects.filter(
#                 tos__organisation=self.request.user.organisation
#             )
#         return self.model.objects.none()


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


@router.register("match-orphans", basename="match-orphans")
class MatchOrphansViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    This view is meant as a service endpoint for matching identity data.
    We can only match emails, so there's no need to check other things.

    It needs IDProxy API key to work and the 'email_in' param
    email_in=<email1>,<email2>,...
    """

    filterset_class = OrphanUserEmailFilter
    serializer_class = serializers.ExternalOrphanSerializer
    permission_classes = (HasIDProxyAPIKey,)
    filter_backends = (DjangoFilterBackend,)

    def get_queryset(self):
        User = get_user_model()
        return (
            User.objects.filter(identity_id__isnull=True)
            .filter(organisation__isnull=False)
            .prefetch_related("organisation")
        )


@router.register("handle-identities", basename="handle-identities")
class HandleIdentitiesViewSet(viewsets.GenericViewSet):
    """
    This view is meant as a service endpoint for merging users to one identity.
    It requires at least 2 identities to match against.

    It needs IDProxy API key to work

    identity_in=<str>,<str>,...
    """

    filterset_class = UserIdentitiesFilter
    permission_classes = (HasIDProxyAPIKey,)
    filter_backends = (DjangoFilterBackend,)

    def get_queryset(self):
        User = get_user_model()
        return (
            User.objects.exclude(identity_id__isnull=True)
            .filter(organisation__isnull=False)
            .prefetch_related("organisation")
        )

    def get_prepped_qs(
        self, raise_exc=True, notification_log=True
    ) -> models.QuerySet[UserType]:
        queryset = self.filter_queryset(self.get_queryset())
        try:
            if queryset.count() > 3 and raise_exc:
                raise exceptions.ValidationError(
                    detail={
                        "identity_in": [
                            f"Merge request has an effect on {queryset.count()} users"
                        ]
                    }
                )
            if (
                OrganisationRoles.objects.filter(user__in=queryset).exists()
                or queryset.filter(is_staff=True).exists()
                or queryset.filter(is_superuser=True).exists()
            ) and raise_exc:
                raise exceptions.ValidationError(
                    detail={
                        "identity_in": [
                            "Merge request has an effect on users with special status. "
                            "This must be handled manually."
                        ]
                    }
                )
            if queryset.values("organisation_id").distinct().count() > 1 and raise_exc:
                raise exceptions.ValidationError(
                    detail={"identity_in": ["Identities from different organisations"]}
                )
        except exceptions.ValidationError as exc:
            # Add event logger here + append queryset info
            if notification_log:
                users = list(queryset)
                notification_logger.warning(
                    f"Merge request encountered problems. Organisation: {users[0].organisation}\n"
                    f"Involved users: {', '.join(str(x) for x in users)}\n"
                    f"Error:\n%s" % exc
                )
            raise exc
        return queryset

    @action(
        methods=["get"], detail=False, serializer_class=serializers.UserQuerySerializer
    )
    def query(self, request):
        queryset = self.get_prepped_qs(raise_exc=False, notification_log=False)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(
        methods=["post"],
        detail=False,
        serializer_class=serializers.MergedIdentitiesSerializer,
    )
    def merge(self, request):
        queryset = self.get_prepped_qs(raise_exc=True, notification_log=True)
        users = list(queryset.order_by("last_login"))
        data = {"moved_to": None, "moved": []}
        if users:
            first = users.pop(0)
            moved_ids = []
            if users:
                for user in users:
                    moved_ids.append(user.identity_id)
                    user.identity_id = first.identity_id
                    user.save()
                data = {"moved_to": first.identity_id, "moved": moved_ids}
                notification_logger.info(
                    f"Merged users in Organisation: {users[0].organisation}\n"
                    f"Target: {first}\n"
                    f"Moved users: {', '.join(str(x) for x in users)}"
                )
        serializer = self.get_serializer(data=data)
        serializer.is_valid()
        return Response(data=serializer.data, status=200)
