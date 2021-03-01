from rest_framework import serializers

from voteit.core.rest_api.serializers import PydanticFieldSerializer
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem


class SpeakerListSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpeakerList
        fields = (
            "pk",
            "title",
            "list_system",
            "agenda_item",
            "state",
        )
        read_only_fields = ("state",)
        extra_kwargs = {
            # At least right now...
            "agenda_item": {"required": True},
            "meeting": {"required": True},
        }


class SpeakerListSystemSerializer(serializers.ModelSerializer):
    settings = PydanticFieldSerializer(allow_null=True, required=False)

    class Meta:
        model = SpeakerListSystem
        fields = (
            "pk",
            "meeting",
            "method_name",
            "title",
            "active",
            "archived",
            "settings",
            "safe_positions",
            "active_list",
        )
        extra_kwargs = {
            # At least right now...
            "meeting": {"required": True},
        }
