from rest_framework import serializers

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


class SpeakerListSystemSerializer(serializers.ModelSerializer):
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
