from __future__ import annotations

from rest_framework import serializers
from rest_framework.serializers import ModelSerializer

from voteit.core.decorators import ensure_atomic
from voteit.room.models import Room
from voteit.room.rest_api.validators import HighlightedValidator


class RoomSerializer(ModelSerializer):
    """
    Used only for basic list read
    """

    pk = serializers.IntegerField(read_only=True)

    class Meta:
        model = Room
        fields = [
            "pk",
        ] + [x.name for x in Room._meta.fields if x.name not in ("id",)]


class RoomHandleSerializer(RoomSerializer):
    """
    For highlighting and handling rooms
    """

    highlighted = serializers.ListSerializer(
        child=serializers.IntegerField(), required=False
    )

    class Meta(RoomSerializer.Meta):
        fields = [
            "pk",
            "highlighted",
            "poll",
            "agenda_item",
        ]
        validators = [
            HighlightedValidator(),
        ]

    def update(self, instance, validated_data):
        highlighted = validated_data.get("highlighted", None)
        if highlighted is not None:
            if highlighted:
                instance.highlighted_proposals.exclude(
                    proposal__in=highlighted
                ).delete()
                for i, prop_id in enumerate(highlighted, start=1):
                    instance.highlighted_proposals.update_or_create(
                        proposal_id=prop_id, defaults={"order": i}
                    )
            else:
                instance.highlighted_proposals.all().delete()
        vd_len = len(validated_data)
        # We DON'T want to save here if no data has changed - it will trigger other events
        if "highlighted" in validated_data and vd_len > 1 or vd_len:
            return super().update(instance, validated_data)
        return instance


class CreateRoomSerializer(RoomSerializer):
    class Meta(RoomSerializer.Meta):
        # WARNING! UniqueTogetherValidator doesn't work if we don't specify fieldnames explicitly.
        # This is a bug in DRF and should be fixed upstreams. Hence, this bs
        fields = [
            "pk",
        ] + [
            x.name
            for x in Room._meta.fields
            if x.name
            not in (
                "id",
                "handler",
            )
        ]

    @ensure_atomic
    def create(self, validated_data) -> Room:
        return super().create(validated_data)


class RoomDetailSerializer(RoomSerializer):
    """
    Used for update and full read
    """

    class Meta(RoomSerializer.Meta):
        # WARNING! UniqueTogetherValidator doesn't work if we don't specify fieldnames explicitly.
        # This is a bug in DRF and should be fixed upstreams. Hence, this bs
        fields = [
            "pk",
        ] + [x.name for x in Room._meta.fields if x.name not in ("id",)]
        read_only_fields = [
            "handler",
            "meeting",
        ]

    @ensure_atomic
    def update(self, instance: Room, validated_data) -> Room:
        return super().update(instance, validated_data)


class SpeakerManagerRoomDetailSerializer(RoomDetailSerializer):
    class Meta(RoomDetailSerializer.Meta):
        fields = [
            "body",
            "open",
            "show_time",
            "send_sls",
        ]


class RoomHighlightedSerializer(RoomSerializer):
    """
    Used when highlighted proposals change
    """

    highlighted = serializers.SerializerMethodField(read_only=True)

    class Meta(RoomSerializer.Meta):
        fields = (
            "pk",
            "highlighted",
        )

    def get_highlighted(self, instance: Room):
        return list(instance.highlighted_proposal_pks)
