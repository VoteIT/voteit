from __future__ import annotations
from typing import List
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _
from rest_framework import serializers

from voteit.components.rest_api.serializers import OrganisationComponentSerializer
from voteit.core.rest_api.fields import SameOrgUserField
from voteit.core.rest_api.serializers import UserSerializer
from voteit.core.rest_api.validators import RoleValidator
from voteit.organisation.models import GlobalTermsOfService
from voteit.organisation.models import OAuth2Provider
from voteit.organisation.models import Organisation
from voteit.organisation.models import OrganisationRoles
from voteit.organisation.models import TermsOfService


if TYPE_CHECKING:
    pass


class OAuth2ProviderSerializer(serializers.Serializer):
    """
    One way of logging in to an organisation.
    """

    provider_id = serializers.CharField(read_only=True)
    title = serializers.SerializerMethodField()
    login_url = serializers.SerializerMethodField()
    profile_url = serializers.SerializerMethodField()
    logout_url = serializers.SerializerMethodField()
    scope = serializers.SerializerMethodField()

    @staticmethod
    def get_title(instance: OAuth2Provider) -> str:
        return instance.backend.get_title()

    @staticmethod
    def get_login_url(instance: OAuth2Provider) -> str:
        return instance.backend.get_login_url(instance)

    @staticmethod
    def get_profile_url(instance: OAuth2Provider) -> str | None:
        return instance.backend.get_profile_url(instance)

    @staticmethod
    def get_logout_url(instance: OAuth2Provider) -> str | None:
        return instance.backend.get_logout_url(instance)

    @staticmethod
    def get_scope(instance: OAuth2Provider) -> List[str]:
        return instance.scope.split()


class OrganisationSerializer(serializers.ModelSerializer):
    providers = serializers.SerializerMethodField()
    components = OrganisationComponentSerializer(
        read_only=True, many=True, source="enabled_components"
    )

    class Meta:
        model = Organisation
        read_only_fields = [
            "active",
            "components",
            "pk",
            "providers",
            "title",
        ]
        fields = read_only_fields + [
            "body",
            "help_info",
            "page_title",
        ]

    @staticmethod
    def get_providers(instance: Organisation) -> List[dict]:
        return OAuth2ProviderSerializer(
            OAuth2Provider.visible_for(instance), many=True
        ).data


# class IDProviderSerializer(serializers.ModelSerializer):
#     pk = serializers.IntegerField(read_only=True)
#
#     class Meta:
#         model = OAuth2Provider
#         exclude = (
#             "client_id",
#             "client_secret",
#         )
#
#
# class IDProviderUpdateSerializer(serializers.ModelSerializer):
#     """
#     This is for internal use, don't use this for external endpoints!
#     """
#
#     pk = serializers.IntegerField(read_only=True)
#
#     class Meta:
#         model = OAuth2Provider
#         fields = "__all__"
#         extra_kwargs = {
#             "provider_id": {"default": "idproxy"},
#             "scope": {"default": "email identity"},
#         }
#
#     def validate_provider_id(self, value):
#         adapters = get_provider_response_adapters()
#         if value not in adapters:
#             raise ValidationError("No provider_id with that name")
#         return value
#
#
# class IDOrganisationSerializer(serializers.ModelSerializer):
#     pk = serializers.IntegerField(read_only=True)
#     provider = IDProviderSerializer(read_only=True)
#
#     class Meta:
#         model = Organisation
#         fields = "__all__"


# class IDOrganisationUpdateSerializer(IDOrganisationSerializer):
#     provider = IDProviderUpdateSerializer()
#
#     class Meta(IDOrganisationSerializer.Meta):
#         pass
#
#     def create(self, validated_data):
#         provider_data = validated_data.pop("provider")
#         with transaction.atomic():
#             provider = OAuth2Provider.objects.create(**provider_data)
#             org = Organisation.objects.create(provider=provider, **validated_data)
#         return org
#
#     def update(self, instance: Organisation, validated_data):
#         provider_data = validated_data.pop("provider")
#         with transaction.atomic():
#             for attr, value in validated_data.items():
#                 setattr(instance, attr, value)
#             instance.save()
#             provider_serializer = IDProviderUpdateSerializer(
#                 instance.provider, data=provider_data, partial=self.partial
#             )
#             provider_serializer.is_valid(raise_exception=True)
#             provider_serializer.save()
#         return instance


class TermsOfServiceSerializer(serializers.ModelSerializer):
    global_body = serializers.CharField(source="based_on.body", read_only=True)

    class Meta:
        model = TermsOfService
        read_only_fields = [
            "based_on",
            "global_body",
            "organisation",
            "pk",
            "version",
        ]
        fields = read_only_fields + ["body"]

    def validate(self, attrs):
        if self.instance is None:
            # New versions are always based on the latest global one
            attrs["based_on"] = GlobalTermsOfService.objects.first()
            if attrs["based_on"] is None:
                raise serializers.ValidationError(
                    _("There are no global terms of service yet")
                )
        return attrs


# class UserConsentSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = UserConsent
#         read_only_fields = ["pk", "user", "tos", "created", "revoked"]
#         fields = read_only_fields
#
#
# class UserConsentCreateSerializer(BaseModelSerializer):
#     author_kw = "user"
#
#     class Meta:
#         model = UserConsent
#         fields = ["tos"]


class OrganisationRolesSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = OrganisationRoles
        fields = read_only_fields = (
            "pk",
            "user",
            "assigned",
        )


class OrgChangeRolesSerializer(serializers.Serializer):
    user = SameOrgUserField()
    roles = serializers.ListField(
        child=serializers.CharField(
            max_length=20, validators=[RoleValidator(roles_cls=OrganisationRoles)]
        )
    )


class ExternalOrphanSerializer(serializers.ModelSerializer):
    """
    Used when returning response to login service.
    Returns information about unclaimed / orphan users that matches
    the external users userdata.
    """

    organisation_host = serializers.CharField(source="organisation.host")

    class Meta:
        model = get_user_model()
        fields = ["email", "organisation_host"]


class UserQuerySerializer(ExternalOrphanSerializer):
    class Meta(ExternalOrphanSerializer.Meta):
        fields = [
            "identity_id",
            "first_name",
            "last_name",
            "pk",
        ] + ExternalOrphanSerializer.Meta.fields


class MergedIdentitiesSerializer(serializers.Serializer):
    moved_to = serializers.CharField()
    moved = serializers.ListSerializer(child=serializers.CharField())
