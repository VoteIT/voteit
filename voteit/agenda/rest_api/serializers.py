from rest_framework import serializers

from voteit.agenda.models import *
from voteit.proposal.rest_api.serializers import ProposalSerializer


class AgendaListSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgendaItem
        fields = 'url', 'pk', 'meeting', 'title', 'state', 'order',
        read_only_fields = 'state', 'order',


class AgendaItemSerializer(serializers.ModelSerializer):
    # proposals = ProposalSerializer(many=True, read_only=True)

    class Meta:
        model = AgendaItem
        fields = 'meeting', 'pk', 'title', 'body', 'state', 'order',  # 'proposals',
        read_only_fields = 'order',
