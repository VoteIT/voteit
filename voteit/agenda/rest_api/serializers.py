from rest_framework import serializers

from voteit.agenda.models import AgendaItem
from voteit.agenda.models import LastRead
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


class ExportAgendaItemSerializer(serializers.ModelSerializer):
    tags = serializers.SerializerMethodField()

    class Meta:
        model = AgendaItem
        fields = (
            "state",
            "pk",
            "title",
            "body",
            "tags",
        )

    def get_tags(self, ai):
        return ",".join(ai.tags)


class LastReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = LastRead
        fields = (
            "agenda_item",
            "timestamp",
        )
