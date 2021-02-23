from rest_framework import serializers

from voteit.agenda.models import AgendaItem


class AgendaListSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgendaItem
        fields = "url", "pk", "meeting", "title", "state", "order"
        read_only_fields = "state", "order"


class AgendaItemSerializer(serializers.ModelSerializer):
    # proposals = ProposalSerializer(many=True, read_only=True)
    # Note: This won't have access to the request, so no url thingies here!

    class Meta:
        model = AgendaItem
        fields = "pk", "meeting", "title", "body", "state", "order"  # 'proposals',
        read_only_fields = ("order",)
