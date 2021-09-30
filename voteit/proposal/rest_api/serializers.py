from rest_framework import serializers

from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.core.rest_api.serializers import RichTextSerializerMixin
from voteit.core.rest_api.validators import ValidateGroupAIContext
from voteit.proposal.models import Proposal

__all__ = ("ProposalDetailSerializer", "ProposalCreateSerializer")


class ProposalDetailSerializer(RichTextSerializerMixin, serializers.ModelSerializer):
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
            "meeting_group",
        ]
        fields = read_only_fields + [
            "body",
            "tags",
            "mentions",
        ]


class ProposalCreateSerializer(RichTextSerializerMixin, BaseModelSerializer):
    class Meta:
        model = Proposal
        fields = [
            "agenda_item",
            "body",
            "meeting_group",
            "tags",
            "mentions",
        ]
        validators = (ValidateGroupAIContext(),)
