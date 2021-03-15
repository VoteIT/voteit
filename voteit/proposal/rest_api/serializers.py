from rest_framework import serializers

from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.proposal.models import Proposal

__all__ = ("ProposalDetailSerializer", "ProposalCreateSerializer")


class ProposalDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proposal
        read_only_fields = [
            "author",
            "created",
            "state",
            "prop_id",
            "state",
            "pk",
            "agenda_item",
            "tags",
            # "group",
        ]
        fields = read_only_fields + [
            "body",
        ]


class ProposalCreateSerializer(BaseModelSerializer):
    class Meta:
        model = Proposal
        fields = [
            "agenda_item",
            "body",
            # "group",
        ]
