from contextlib import suppress
from typing import Optional
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers
from rest_framework.reverse import reverse
from rest_framework.exceptions import ValidationError
from typing import List
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.organisation.models import OAuth2Provider
from voteit.organisation.models import Organisation
from voteit.organisation.models import TermsOfService
from voteit.organisation.models import UserConsent
from voteit.organisation.utils import get_provider_response_adapters


class OrganisationSerializer(serializers.ModelSerializer):
    login_url = serializers.SerializerMethodField()
    id_host = serializers.SerializerMethodField()
    scope = serializers.SerializerMethodField()

    class Meta:
        model = Organisation
        read_only_fields = ["pk", "login_url", "scope", "id_host"]
        fields = read_only_fields + ["title", "body"]

    def get_login_url(self, instance: Organisation) -> Optional[str]:
        with suppress(ObjectDoesNotExist):
            if instance.provider:
                return reverse(
                    "begin-auth",
                    args=[instance.pk],
                    request=self.context.get("request"),
                )

    @staticmethod
    def get_id_host(instance: Organisation) -> Optional[str]:
        if host := getattr(settings, "ID_HOST", None):
            return host
        with suppress(ObjectDoesNotExist):
            url = urlparse(instance.provider.auth_url)
            return f"{url.scheme}://{url.netloc}"

    @staticmethod
    def get_scope(instance: Organisation) -> List[str]:
        with suppress(ObjectDoesNotExist):
            if instance.provider:
                return instance.provider.scope.split()
        return []


class IDOrganisationSerializer(serializers.ModelSerializer):
    pk = serializers.IntegerField(read_only=True)

    class Meta:
        model = Organisation
        fields = "__all__"


class IDProviderSerializer(serializers.ModelSerializer):
    pk = serializers.IntegerField(read_only=True)

    class Meta:
        model = OAuth2Provider
        exclude = (
            "client_id",
            "client_secret",
        )


class IDProviderUpdateSerializer(serializers.ModelSerializer):
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
