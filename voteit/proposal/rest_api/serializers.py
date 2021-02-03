from rest_framework import serializers
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.proposal import models


class ProposalListSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Proposal
        fields = (
            "url",
            "pk",
            "body",
            "state",
            "agenda_item",
            "author",
            "polls",
            "prop_id",
        )


class ProposalDetailSerializer(BaseModelSerializer):
    # Note: This won't have access to the request, so no url thingies here!

    class Meta(ProposalListSerializer.Meta):
        fields = (
            "pk",
            "created",
            "body",
            "state",
            "agenda_item",
            "author",
            "polls",
            "prop_id",
            "tags",
        )
        read_only_fields = (
            "created",
            "state",
            "author",
            "polls",
            "prop_id",
            "tags",
        )
