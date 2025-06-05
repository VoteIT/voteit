from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from django.db import models
from rest_framework import serializers
from rest_framework import exceptions
from rest_framework.exceptions import ValidationError

from voteit.core.rest_api.fields import RolesField
from voteit.core.rest_api.serializers import PydanticFieldSerializer
from voteit.core.rest_api.utils import perm_denied_msg
from voteit.meeting.models import MeetingRoles
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.utils import get_list_method_registry

if TYPE_CHECKING:
    from voteit.speaker.abcs import ListMethod
    from voteit.room.models import Room


def _validate_add(serializer, model: type, value):
    # FIXME: Generalize later on
    perm = serializer.context["view"].get_model_perm(model, "add")
    user = serializer.context["request"].user
    if not user.has_perm(perm, value):
        raise exceptions.PermissionDenied(perm_denied_msg(perm, value))


class CreateSpeakerListSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpeakerList
        read_only_fields = [
            "state",
            "pk",
        ]
        fields = read_only_fields + [
            "agenda_item",
            "speaker_system",
            "title",
        ]

    def validate_speaker_system(self, value: SpeakerListSystem):
        _validate_add(self, SpeakerList, value)
        return value

    def validate(self, attrs):
        if ai := attrs.get("agenda_item"):
            if ai.meeting_id != attrs["speaker_system"].meeting_id:
                raise ValidationError(
                    "SpeakerListSystem and AgendaItem belong to different meetings."
                )
        return attrs


class SpeakerListSerializer(serializers.ModelSerializer):
    class Meta(CreateSpeakerListSerializer.Meta):
        read_only_fields = [
            "state",
            "agenda_item",
            "speaker_system",
        ]

    # def get_queue(self, instance: SpeakerList) -> list[int]:
    #    return instance.order_list

    # def get_current(self, instance: SpeakerList) -> int | None:
    #    return
    # FIXME:XXXX
    # with suppress(Speaker.DoesNotExist):
    #    if instance.current:
    #        return instance.current.user_id


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
            "active_list",
        ]
        fields = [
            "method_name",
            "settings",
            "safe_positions",
            "room",
            "meeting_roles_to_speaker",
            "show_time",
        ] + read_only_fields

    def validate_method_name(self, value):
        if value not in get_list_method_registry():
            raise exceptions.ValidationError(f"No list method_name {value}")
        return value

    def validate_room(self, value: Room):
        _validate_add(self, SpeakerListSystem, value)
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
            if not isinstance(settings, dict):
                attrs["settings"] = settings = {}
            try:
                method.settings_schema(**settings)
            except ValueError as exc:
                raise exceptions.ValidationError({"settings": [str(exc)]})
        return super().validate(attrs)


class SystemRelatedListsPKField(serializers.PrimaryKeyRelatedField):
    """
    Only works as field on SpeakerSystem serializers
    """

    def get_queryset(self) -> models.QuerySet[SpeakerList]:
        return self.root.instance.speaker_lists.all()


class SpeakerListSystemSerializer(CreateSpeakerListSystemSerializer):
    active_list = SystemRelatedListsPKField(required=False, allow_null=True)

    class Meta(CreateSpeakerListSystemSerializer.Meta):
        # active_list ok to change here
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
