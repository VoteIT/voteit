from rest_framework import serializers
from voteit.organisation.models import Organisation
from voteit.organisation.models import TermsOfService
from voteit.organisation.models import UserConsent


class OrganisationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organisation
        fields = ["pk", "title", "providers"]


class TOSSerializer(serializers.ModelSerializer):
    class Meta:
        model = TermsOfService
        fields = "__all__"


class UserConsentSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserConsent
        fields = "__all__"
