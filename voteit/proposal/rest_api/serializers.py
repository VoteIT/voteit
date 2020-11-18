from rest_framework import serializers
from voteit.proposal import models


class ProposalListSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Proposal
        fields = "url", "pk", "title", "state", "agenda_item", "author"
        read_only_fields = ("state",)


class ProposalDetailSerializer(serializers.ModelSerializer):
    # Note: This won't have access to the request, so no url thingies here!

    class Meta:
        model = models.Proposal
        fields = "pk", "title", "body", "state", "agenda_item", "author"
        read_only_fields = ("state", "author")

    def create(self, validated_data):
        return models.Proposal.objects.create(
            author=self.context['request'].user,
            **validated_data
        )
