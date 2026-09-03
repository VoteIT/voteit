from django.utils.translation import gettext as _
from rest_framework import serializers

from voteit.agenda.models import AgendaItem
from voteit.agenda.models import LastRead
from voteit.agenda.statemachines import AgendaItemStateMachine
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.core.rest_api.serializers import RichTextSerializerMixin
from voteit.core.rest_api.utils import validate_model_add
from voteit.meeting.rest_api.fields import ModeratorMeetingField


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
            "id",
            "related_modified",
            "mentions",
            "state",
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
        fields = read_only_fields = (
            "agenda_item",
            "timestamp",
        )


class BulkAgendaItemSerializer(serializers.Serializer):
    meeting = ModeratorMeetingField()
    # Capped since state-machine guards (moderator + ongoing-poll checks) run
    # once per item - keeps that bounded rather than unbounded.
    agenda_items = serializers.ListField(
        child=serializers.IntegerField(), min_length=1, max_length=250
    )

    def validate_agenda_items(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError(
                _("Duplicate agenda item IDs are not allowed.")
            )
        return value

    def validate(self, attrs):
        meeting = attrs["meeting"]
        pks = attrs["agenda_items"]
        items = list(AgendaItem.objects.filter(pk__in=pks, meeting=meeting))
        if len(items) != len(pks):
            raise serializers.ValidationError(
                {
                    "agenda_items": _(
                        "One or more agenda items not found in the specified meeting."
                    )
                }
            )
        # Avoid a per-item query for `meeting` within state machine guards
        for ai in items:
            ai.meeting = meeting
        attrs["agenda_items"] = items
        return attrs


class BulkAgendaItemChangeSerializer(BulkAgendaItemSerializer):
    state = serializers.ChoiceField(
        choices=[(s.value, s.name) for s in AgendaItemStateMachine.states],
        required=False,
        allow_null=True,
        default=None,
    )
    block_discussion = serializers.BooleanField(
        required=False, allow_null=True, default=None
    )
    block_proposals = serializers.BooleanField(
        required=False, allow_null=True, default=None
    )

    def validate(self, attrs):
        if all(
            attrs.get(x) is None
            for x in ("state", "block_discussion", "block_proposals")
        ):
            raise serializers.ValidationError(
                _("state, block_discussion or block_proposals required")
            )
        return super().validate(attrs)


class BulkAgendaItemDeleteSerializer(BulkAgendaItemSerializer):
    def validate_meeting(self, meeting):
        if meeting.is_ongoing:
            raise serializers.ValidationError(_("Can't bulk delete in ongoing meeting"))
        return meeting
