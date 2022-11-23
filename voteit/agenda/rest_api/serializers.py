from rest_framework import serializers

from voteit.agenda.models import AgendaItem
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.core.rest_api.serializers import RichTextSerializerMixin


class AgendaItemSerializer(RichTextSerializerMixin, BaseModelSerializer):
    pk = serializers.IntegerField(read_only=True)

    class Meta:
        model = AgendaItem
        read_only_fields = (
            "author",
            "meeting",
            "mentions",
            "order",
            "related_modified",
            "state",
            "pk",
        )
        exclude = (
            "author",
            "last_modified_by",
        )


class CreateAgendaItemSerializer(AgendaItemSerializer):
    class Meta(AgendaItemSerializer.Meta):
        read_only_fields = (
            "mentions",
            "order",
            "related_modified",
            "state",
        )
