from contextlib import suppress
from typing import List
from typing import Optional

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.reverse import reverse

from voteit.components.rest_api.serializers import OrganisationComponentSerializer
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.core.rest_api.serializers import UserSerializer
from voteit.organisation.models import OAuth2Provider
from voteit.organisation.models import Organisation
from voteit.organisation.models import OrganisationRoles
from voteit.organisation.models import TermsOfService
from voteit.organisation.models import UserConsent
from voteit.organisation.utils import get_provider_response_adapters


class OrganisationSerializer(serializers.ModelSerializer):
    login_url = serializers.SerializerMethodField()
    id_host = serializers.SerializerMethodField()
    scope = serializers.SerializerMethodField()
    components = OrganisationComponentSerializer(
        read_only=True, many=True, source="enabled_components"
    )

    class Meta:
        model = Organisation
        read_only_fields = ["pk", "login_url", "scope", "id_host", "title"]
        fields = read_only_fields + ["page_title", "body", "components"]

    def get_login_url(self, instance: Organisation) -> Optional[str]:
        with suppress(ObjectDoesNotExist):
            if instance.provider:
                return reverse(
                    "begin-auth",
                    request=self.context.get("request"),
                )

    @staticmethod
    def get_id_host(instance: Organisation) -> Optional[str]:
        return settings.ID_HOST

    @staticmethod
    def get_scope(instance: Organisation) -> List[str]:
        with suppress(ObjectDoesNotExist):
            if instance.provider:
                return instance.provider.scope.split()
        return []


class IDProviderSerializer(serializers.ModelSerializer):
    pk = serializers.IntegerField(read_only=True)

    class Meta:
        model = OAuth2Provider
        exclude = (
            "client_id",
            "client_secret",
        )


class IDProviderUpdateSerializer(serializers.ModelSerializer):
    """
    This is for internal use, don't use this for external endpoints!
    """

    pk = serializers.IntegerField(read_only=True)

    class Meta:
        model = OAuth2Provider
        fields = "__all__"
        extra_kwargs = {
            "provider_id": {"default": "idproxy"},
            "scope": {"default": "email identity"},
        }

    def validate_provider_id(self, value):
        adapters = get_provider_response_adapters()
        if value not in adapters:
            raise ValidationError("No provider_id with that name")
        return value


class IDOrganisationSerializer(serializers.ModelSerializer):
    pk = serializers.IntegerField(read_only=True)
    provider = IDProviderSerializer(read_only=True)

    class Meta:
        model = Organisation
        fields = "__all__"


class IDOrganisationUpdateSerializer(IDOrganisationSerializer):
    provider = IDProviderUpdateSerializer()

    class Meta(IDOrganisationSerializer.Meta):
        pass

    def create(self, validated_data):
        provider_data = validated_data.pop("provider")
        with transaction.atomic():
            provider = OAuth2Provider.objects.create(**provider_data)
            org = Organisation.objects.create(provider=provider, **validated_data)
        return org

    def update(self, instance: Organisation, validated_data):
        provider_data = validated_data.pop("provider")
        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()
            provider_serializer = IDProviderUpdateSerializer(
                instance.provider, data=provider_data, partial=self.partial
            )
            provider_serializer.is_valid(raise_exception=True)
            provider_serializer.save()
        return instance


class TOSSerializer(serializers.ModelSerializer):
    class Meta:
        model = TermsOfService
        read_only_fields = [
            "pk",
            "organisation",
        ]
        fields = read_only_fields + [
            "required",
            "title",
            "body",
        ]


class TOSCreateSerializer(BaseModelSerializer):
    class Meta:
        model = TermsOfService
        fields = "__all__"


class UserConsentSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserConsent
        read_only_fields = ["pk", "user", "tos", "created", "revoked"]
        fields = read_only_fields


class UserConsentCreateSerializer(BaseModelSerializer):
    author_kw = "user"

    class Meta:
        model = UserConsent
        fields = ["tos"]


class OrganisationRolesSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = OrganisationRoles
        fields = read_only_fields = "pk", "user", "assigned"
