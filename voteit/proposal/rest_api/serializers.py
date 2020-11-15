from rest_framework import serializers
from voteit.proposal import models


class ProposalSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Proposal
        fields = 'url', 'title', 'state', 'agenda_item'
        read_only_fields = 'state',
