from contextlib import suppress

from rest_framework import serializers
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.organisation.models import Organisation
from voteit.organisation.models import TermsOfService
from voteit.organisation.models import UserConsent
from voteit.organisation.models import OAuth2Provider


class OrganisationSerializer(serializers.ModelSerializer):
    login_url = serializers.SerializerMethodField()

    class Meta:
        model = Organisation
        read_only_fields = ["pk", "login_url"]
        fields = read_only_fields + ["title", "body"]

    def get_login_url(self, instance: Organisation):
        with suppress(OAuth2Provider.DoesNotExist):  # Oh django
            if instance.provider:
                return f"/begin-auth/{instance.pk}/"


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
