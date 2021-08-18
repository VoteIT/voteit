from datetime import datetime
from typing import Optional

from rest_framework import serializers

from voteit.agenda.models import AgendaItem
from voteit.core.rest_api.serializers import BaseModelSerializer


class AgendaItemSerializer(BaseModelSerializer):
    # proposals = ProposalSerializer(many=True, read_only=True)
    # Note: This won't have access to the request, so no url thingies here!
    # FIXME: This needs testing and separation - one serializer for create and one for the other
    class Meta:
        model = AgendaItem
        read_only_fields = ("order", "related_modified")
        fields = read_only_fields + (
            "pk",
            "meeting",
            "title",
            "body",
            "state",
            "block_proposals",
            "block_discussion",
        )
