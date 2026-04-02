from __future__ import annotations

from django.core.exceptions import ValidationError
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer

from voteit.core.decorators import ensure_atomic
from voteit.core.rest_api.utils import validate_model_add
from voteit.proposal.models import Proposal
from voteit.room.models import Room


class RoomSerializer(ModelSerializer):
    """
    Used only for basic list read
    """

    pk = serializers.IntegerField(read_only=True)

    class Meta:
        model = Room
        fields = read_only_fields = [
            "pk",
        ] + [x.name for x in Room._meta.fields if x.name not in ("id",)]


class RoomHandleSerializer(ModelSerializer):
    """
    For highlighting and handling rooms
    """

    highlighted = serializers.ListSerializer(
        child=serializers.IntegerField(), required=False
    )

    class Meta:
        model = Room
        fields = [
            "pk",
            "highlighted",
            "poll",
            "agenda_item",
            "show_ballot",
        ]

    def validate(self, attrs):
        if highlighted := attrs.get("highlighted"):
            prop_pks = set(
                Proposal.objects.filter(
                    agenda_item__meeting_id=self.instance.meeting_id
                ).values_list("pk", flat=True)
            )
            if missing := set(highlighted) - prop_pks:
                raise ValidationError(
                    {
                        "highlighted": [
                            "The following proposals don't exist withing this "
                            "meeting: %s" % ", ".join(str(x) for x in missing)
                        ]
                    }
                )
        return attrs

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
            instance.signal_highlighted()
        # We DON'T want to save here if no data has changed - it will trigger other events
        vd_len = len(validated_data)
        if "highlighted" in validated_data:
            if vd_len > 1:
                return super().update(instance, validated_data)
        elif vd_len:
            return super().update(instance, validated_data)
        return instance


class CreateRoomSerializer(RoomSerializer):
    class Meta:
        # WARNING! UniqueTogetherValidator doesn't work if we don't specify fieldnames explicitly.
        model = Room
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

    def validate_meeting(self, value):
        validate_model_add(self, Room, value)
        return value

    @ensure_atomic
    def create(self, validated_data) -> Room:
        return super().create(validated_data)


class RoomDetailSerializer(RoomSerializer):
    """
    Used for update and full read
    """

    class Meta:
        model = Room
        # WARNING! UniqueTogetherValidator doesn't work if we don't specify fieldnames explicitly.
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
    class Meta:
        model = Room
        fields = [
            "body",
            "open",
            "show_time",
            "send_sls",
        ]
