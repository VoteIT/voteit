from __future__ import annotations

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from voteit.components.models import MeetingComponent
from voteit.components.models import OrganisationComponent
from voteit.components.utils import get_meeting_component_adapters
from voteit.core.rest_api.serializers import PydanticFieldSerializer
from voteit.core.rest_api.utils import meeting_from_unsafe_data
from voteit.core.rest_api.utils import validate_model_add
from voteit.meeting.models import Meeting


class ComponentSerializer(serializers.ModelSerializer):
    pk = serializers.IntegerField(read_only=True)
    settings = PydanticFieldSerializer(allow_null=True, required=False)

    class Meta:
        exclude = ("id", "settings_data")

    def validate_settings(self, value):
        if self.instance is None:
            return value
        schema = self.instance.adapter.schema
        if schema:
            try:
                schema(**value)
            except ValueError as exc:
                raise ValidationError(str(exc))
        else:
            if value is not None:
                raise ValidationError("Component has no schema, so no settings allowed")
        return value

    def validate(self, attrs):
        if self.instance and attrs.get("enabled"):
            if not self.instance.valid_component_name():
                raise ValidationError({"enabled": "Component name is not registered"})
            if "settings" not in attrs and not self.instance.valid_settings():
                raise ValidationError({"enabled": "Component settings are not valid"})
        return attrs


class CreateMeetingComponentSerializer(ComponentSerializer):
    class Meta(ComponentSerializer.Meta):
        model = MeetingComponent

    def validate_component_name(self, value: str):
        registry = get_meeting_component_adapters()
        if value not in registry:
            raise ValidationError("No such component name")
        meeting = meeting_from_unsafe_data(self)
        if meeting.components.filter(component_name=value).exists():
            raise ValidationError(
                "Only one of these components are allowed per meeting."
            )
        return value

    def validate_meeting(self, value: Meeting):
        validate_model_add(self, MeetingComponent, value)
        return value


class MeetingComponentSerializer(CreateMeetingComponentSerializer):
    is_valid = serializers.BooleanField(read_only=True)
    instance: MeetingComponent

    class Meta(CreateMeetingComponentSerializer.Meta):
        read_only_fields = ["component_name", "meeting"]


class OrganisationComponentSerializer(ComponentSerializer):
    is_valid = serializers.BooleanField(read_only=True)
    instance: OrganisationComponent

    class Meta(ComponentSerializer.Meta):
        model = OrganisationComponent


class VerboseComponentSerializer(serializers.Serializer):
    schema = serializers.SerializerMethodField()

    def get_schema(self, instance: MeetingComponent):
        if instance.adapter and instance.adapter.schema is not None:
            return instance.adapter.schema.model_json_schema()


class VerboseMeetingComponentSerializer(
    MeetingComponentSerializer, VerboseComponentSerializer
): ...


class VerboseOrganisationComponentSerializer(
    OrganisationComponentSerializer, VerboseComponentSerializer
): ...
