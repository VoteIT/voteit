from rest_framework import serializers
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.proposal import models


class ProposalListSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Proposal
        fields = "url", "pk", "title", "state", "agenda_item", "author"
        read_only_fields = ("state",)


class ProposalDetailSerializer(BaseModelSerializer):
    # Note: This won't have access to the request, so no url thingies here!

    class Meta:
        model = models.Proposal
        fields = "pk", "title", "body", "state", "agenda_item", "author"
        read_only_fields = ("state", "author")
