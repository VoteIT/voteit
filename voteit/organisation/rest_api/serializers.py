from contextlib import suppress
from typing import Optional

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers
from rest_framework.reverse import reverse
from typing import List
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.organisation.models import Organisation
from voteit.organisation.models import TermsOfService
from voteit.organisation.models import UserConsent


class OrganisationSerializer(serializers.ModelSerializer):
    login_url = serializers.SerializerMethodField()
    scope = serializers.SerializerMethodField()

    class Meta:
        model = Organisation
        read_only_fields = ["pk", "login_url", "scope"]
        fields = read_only_fields + ["title", "body"]

    def get_login_url(self, instance: Organisation) -> Optional[str]:
        with suppress(ObjectDoesNotExist):
            if instance.provider:
                return reverse(
                    "begin-auth",
                    args=[instance.pk],
                    request=self.context.get("request"),
                )

    def get_scope(self, instance: Organisation) -> List[str]:
        with suppress(ObjectDoesNotExist):
            if instance.provider:
                return instance.provider.scope.split()
        return []


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
