from typing import List

from rest_framework import serializers
from rest_framework import exceptions

from voteit.core.rest_api.serializers import PydanticFieldSerializer
from voteit.meeting.models import MeetingRoles
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem


class SpeakerListSerializer(serializers.ModelSerializer):
    # FIXME: Don't allow system and agenda items to be within different meetings
    # It's at least prevented in .save() right now
    class Meta:
        model = SpeakerList
        read_only_fields = [
            "state",
        ]
        fields = [
            "pk",
            "title",
            "speaker_system",
            "agenda_item",
        ] + read_only_fields
        extra_kwargs = {
            # At least right now...
            "agenda_item": {"required": True},
            "meeting": {"required": True},
        }


class HistoricSpeakerListSerializer(serializers.Serializer):
    user = serializers.IntegerField()
    times_spoken = serializers.IntegerField()
    seconds_spoken = serializers.IntegerField()

    class Meta:
        # model = Speaker
        fields = ("user", "times_spoken", "seconds_spoken")
        read_only_fields = fields


class SpeakerListSystemSerializer(serializers.ModelSerializer):
    settings = PydanticFieldSerializer(allow_null=True, required=False)

    class Meta:
        model = SpeakerListSystem
        read_only_fields = ["state"]
        fields = [
            "pk",
            "meeting",
            "method_name",
            "title",
            "settings",
            "active_list",
            "safe_positions",
            "meeting_roles_to_speaker",
        ] + read_only_fields
        extra_kwargs = {
            # At least right now...
            "meeting": {"required": True},
        }

    def validate_meeting_roles_to_speaker(self, value):
        for role in value:
            if role not in MeetingRoles.valid_roles:
                raise exceptions.ValidationError(f"{role} is not a valid meeting role")
        return value
