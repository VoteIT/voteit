from rest_framework import serializers
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.organisation.models import Organisation
from voteit.organisation.models import TermsOfService
from voteit.organisation.models import UserConsent


class OrganisationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organisation
        # FIXME: Providers here?
        read_only_fields = ["providers", "pk"]
        fields = read_only_fields + ["title", "body"]


# class OrganisationCreateSerializer(BaseModelSerializer):
#     class Meta:
#         model = Organisation
#         fields = []


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
