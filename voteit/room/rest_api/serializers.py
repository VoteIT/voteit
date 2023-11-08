from rest_framework import serializers
from rest_framework.serializers import ModelSerializer
from rest_framework.validators import UniqueTogetherValidator

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


class RoomDetailSerializer(RoomSerializer):
    """
    Used for create and full read
    """

    highlighted = serializers.ListSerializer(
        child=serializers.IntegerField(), required=False
    )

    class Meta(RoomSerializer.Meta):
        # WARNING! UniqueTogetherValidator doesn't work if we don't specify fieldnames explicitly.
        # This is a bug in DRF and should be fixed upstreams. Hence, this bs
        fields = [
            "pk",
            "highlighted",
        ] + [x.name for x in Room._meta.fields if x.name not in ("id",)]
        validators = [
            HighlightedValidator(),
        ]

    @ensure_atomic
    def create(self, validated_data) -> Room:
        highlighted = validated_data.pop("highlighted", None)
        instance = super().create(validated_data)
        if highlighted:
            for i, prop_id in enumerate(highlighted, start=1):
                instance.highlighted_proposals.update_or_create(
                    proposal_id=prop_id, defaults={"order": i}
                )
        return instance

    @ensure_atomic
    def update(self, instance: Room, validated_data) -> Room:
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
        validated_data.pop("meeting", None)  # Can't be changed later on
        return super().update(instance, validated_data)


class RoomHighlightedSerializer(RoomSerializer):
    """
    Used when highlighted proposals change
    """

    highlighted = serializers.SerializerMethodField(read_only=True)

    class Meta(RoomSerializer.Meta):
        fields = (
            "pk",
            "highlighted",
            "agenda_item",
        )

    def get_highlighted(self, instance: Room):
        return list(instance.highlighted_proposal_pks)
