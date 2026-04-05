from rest_framework import serializers

from voteit.agenda.models import AgendaItem
from voteit.agenda.models import LastRead
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.core.rest_api.serializers import RichTextSerializerMixin
from voteit.core.rest_api.utils import validate_model_add


class AgendaItemSerializer(RichTextSerializerMixin, BaseModelSerializer):
    add_body_tags = False
    pk = serializers.IntegerField(read_only=True)

    class Meta:
        model = AgendaItem
        read_only_fields = (
            "meeting",
            "order",
            "related_modified",
            "state",
            "pk",
        )
        exclude = (
            "id",
            "author",
            "mentions",
            "last_modified_by",
        )


class AgendaItemListSerializer(AgendaItemSerializer):
    """
    Serializer for meeting app_state - excludes body
    """

    class Meta:
        model = AgendaItem
        fields = read_only_fields = (
            "block_discussion",
            "block_proposals",
            "meeting",
            "order",
            "pk",
            "related_modified",
            "state",
            "tags",
            "title",
        )


class AgendaItemBodySerializer(AgendaItemSerializer):
    """
    Serializer for agenda_item app_state
    """

    class Meta:
        model = AgendaItem
        fields = read_only_fields = (
            "body",
            "pk",
        )


class CreateAgendaItemSerializer(AgendaItemSerializer):
    class Meta(AgendaItemSerializer.Meta):
        read_only_fields = []
        exclude = (
            "author",
            "related_modified",
            "mentions",
            "state",
            "last_modified_by",
        )

    def validate_meeting(self, meeting):
        validate_model_add(self, AgendaItem, meeting)
        return meeting


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
