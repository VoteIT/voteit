from rest_framework import serializers
from voteit.organisation.models import Organisation


class OrganisationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organisation
        fields = ["pk", "title", "providers"]
