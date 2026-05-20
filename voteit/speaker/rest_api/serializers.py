from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework import exceptions
from rest_framework.exceptions import ValidationError

from voteit.core.rest_api.fields import RolesField
from voteit.core.rest_api.fields import SameOrgUserField
from voteit.core.rest_api.serializers import PydanticFieldSerializer
from voteit.core.rest_api.serializers import UserListSerializer
from voteit.core.rest_api.utils import validate_model_add
from voteit.core.rest_api.validators import RoleValidator
from voteit.meeting.models import MeetingRoles
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.models import SpeakerSystemRoles
from voteit.speaker.utils import get_list_method_registry

if TYPE_CHECKING:
    from voteit.speaker.abcs import ListMethod
    from voteit.room.models import Room

User = get_user_model()


class SpeakerSystemField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        return SpeakerListSystem.objects.filter(
            meeting__participants=self.context["request"].user
        )


class SpeakerSystemRolesSerializer(serializers.ModelSerializer):
    speaker_system = serializers.IntegerField(source="context_id", read_only=True)
    user = UserListSerializer(read_only=True)
    assigned = serializers.ListSerializer(child=serializers.CharField(), read_only=True)

    class Meta:
        model = SpeakerSystemRoles
        fields = read_only_fields = ("pk", "user", "speaker_system", "assigned")


class SpeakerChangeRolesSerializer(serializers.Serializer):
    speaker_system = SpeakerSystemField()
    user = SameOrgUserField()
    roles = serializers.ListField(
        child=serializers.CharField(
            max_length=30, validators=[RoleValidator(roles_cls=SpeakerSystemRoles)]
        )
    )


class CreateSpeakerListSerializer(serializers.ModelSerializer):
    queue = serializers.SerializerMethodField()
    current = serializers.SerializerMethodField()

    class Meta:
        model = SpeakerList
        read_only_fields = [
            "state",
            "pk",
            "queue",
            "current",
            "meeting",
            "room",
        ]
        fields = read_only_fields + [
            "agenda_item",
            "speaker_system",
            "title",
        ]

    def get_current(self, instance: SpeakerList) -> int | None:
        """
        Return User PK for currently speaking user.
        """
        if speaker := instance.active_speaker():
            return speaker.user_id

    def validate_speaker_system(self, value: SpeakerListSystem):
        validate_model_add(self, SpeakerList, value)
        return value

    def validate(self, attrs):
        if ai := attrs.get("agenda_item"):
            if ai.meeting_id != attrs["speaker_system"].meeting_id:
                raise ValidationError(
                    {
                        "agenda_item": [
                            "SpeakerListSystem and AgendaItem belong to different meetings."
                        ]
                    }
                )
        return attrs

    def get_queue(self, instance: SpeakerList) -> list[int]:
        return instance.order_list


class SpeakerListSerializer(CreateSpeakerListSerializer):
    class Meta(CreateSpeakerListSerializer.Meta):
        read_only_fields = [
            "state",
            "agenda_item",
            "speaker_system",
            "meeting",
            "room",
        ]


class HistoricSpeakerListSerializer(serializers.Serializer):
    user = serializers.IntegerField()
    times_spoken = serializers.IntegerField()
    seconds_spoken = serializers.IntegerField()

    class Meta:
        # model = Speaker
        fields = ("user", "times_spoken", "seconds_spoken")
        read_only_fields = fields


class CreateSpeakerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Speaker
        read_only_fields = [
            "pk",
            "started",
            "seconds",
        ]
        fields = [
            "user",
            "speaker_list",
        ] + read_only_fields

    def validate_speaker_list(self, value: SpeakerList):
        validate_model_add(self, Speaker, value)
        return value

    def validate(self, attrs):
        speaker_list = attrs["speaker_list"]
        user = attrs["user"]
        if speaker_list.speaker_items.filter(seconds__isnull=True, user=user).exists():
            raise ValidationError({"user": _("User already in list.")})
        if not user.meeting_roles.filter(context=speaker_list.meeting):
            raise ValidationError(
                {"user": _("User isn't a participant in this meeting.")}
            )
        return attrs


class SpeakerSerializer(serializers.ModelSerializer):
    room = serializers.PrimaryKeyRelatedField(
        source="speaker_list.room", read_only=True
    )

    class Meta:
        model = Speaker
        read_only_fields = [
            "user",
            "speaker_list",
            "started",
            "room",
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
        validate_model_add(self, SpeakerListSystem, value)
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
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")
    email = serializers.CharField(source="user.email")
    userid = serializers.CharField(source="user.userid")
    agenda_item = serializers.SerializerMethodField()
    speaker_list = serializers.CharField(source="speaker_list.title")

    class Meta:
        model = Speaker
        exclude = ("id", "user")

    def get_agenda_item(self, obj) -> str:
        if obj.speaker_list.agenda_item_id:
            return obj.speaker_list.agenda_item.title
        return ""
