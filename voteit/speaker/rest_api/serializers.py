from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from rest_framework import serializers
from rest_framework import exceptions

from voteit.core.rest_api.fields import RolesField
from voteit.core.rest_api.serializers import PydanticFieldSerializer
from voteit.meeting.models import MeetingRoles
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.utils import get_list_method_registry

if TYPE_CHECKING:
    from voteit.speaker.abcs import ListMethod


class SpeakerListSerializer(serializers.ModelSerializer):
    queue = serializers.SerializerMethodField()
    current = serializers.SerializerMethodField()

    # FIXME: Don't allow system and agenda items to be within different meetings
    # It's at least prevented in .save() right now
    class Meta:
        model = SpeakerList
        read_only_fields = [
            "state",
            "queue",
            "current",
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

    def get_queue(self, instance: SpeakerList) -> list[int]:
        return instance.order_list

    def get_current(self, instance: SpeakerList) -> int | None:
        with suppress(Speaker.DoesNotExist):
            if instance.current:
                return instance.current.user_id


class HistoricSpeakerListSerializer(serializers.Serializer):
    user = serializers.IntegerField()
    times_spoken = serializers.IntegerField()
    seconds_spoken = serializers.IntegerField()

    class Meta:
        # model = Speaker
        fields = ("user", "times_spoken", "seconds_spoken")
        read_only_fields = fields


class SpeakerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Speaker
        read_only_fields = [
            "user",
            "speaker_list",
            "started",
            "pk",
        ]
        fields = ["seconds"] + read_only_fields


class CreateSpeakerListSystemSerializer(serializers.ModelSerializer):
    settings = PydanticFieldSerializer(allow_null=True, required=False)
    meeting_roles_to_speaker = RolesField(
        required=False, valid_roles=set(MeetingRoles.valid_roles.values())
    )

    class Meta:
        model = SpeakerListSystem
        read_only_fields = [
            "state",
            "meeting",
            "pk",
        ]
        fields = [
            "method_name",
            "settings",
            "active_list",
            "safe_positions",
            "room",
            "meeting_roles_to_speaker",
            "show_time",
        ] + read_only_fields

    def validate_method_name(self, value):
        if value not in get_list_method_registry():
            raise exceptions.ValidationError(f"No list method_name {value}")
        return value

    def validate(self, attrs):
        method_name = attrs.get("method_name")
        if not method_name:
            # Shouldn't happen
            method_name = self.instance.method_name
        reg = get_list_method_registry()
        method: ListMethod = reg[method_name]
        if method.settings_schema is None:
            attrs.pop("settings", None)
        else:
            settings = attrs.get("settings", {})
            try:
                method.settings_schema(**settings)
            except ValueError as exc:
                raise exceptions.ValidationError({"settings": [str(exc)]})
        return super().validate(attrs)


class SpeakerListSystemSerializer(CreateSpeakerListSystemSerializer):
    class Meta(CreateSpeakerListSystemSerializer.Meta):
        read_only_fields = [
            "pk",
            "state",
            "room",
            "meeting",
        ]


class SpeakerExportSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.CharField()
    userid = serializers.CharField()

    class Meta:
        model = Speaker
        exclude = ("id", "user")
