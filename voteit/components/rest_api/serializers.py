from __future__ import annotations

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from voteit.components.models import MeetingComponent
from voteit.components.utils import get_meeting_component_adapters
from voteit.core.rest_api.serializers import PydanticFieldSerializer
from voteit.core.rest_api.utils import meeting_from_unsafe_data


class CreateMeetingComponentSerializer(serializers.ModelSerializer):
    pk = serializers.IntegerField(read_only=True)
    settings = PydanticFieldSerializer(allow_null=True, required=False)

    class Meta:
        model = MeetingComponent
        exclude = ("id", "settings_data")
        read_only_fields = ["state"]

    def validate_component_name(self, value: str):
        registry = get_meeting_component_adapters()
        if value not in registry:
            raise ValidationError("No such component name")
        # Will raise error if meeting doesn't exist
        meeting = meeting_from_unsafe_data(self)
        if meeting.components.filter(component_name=value).exists():
            raise ValidationError(
                "Only one of these components are allowed per meeting."
            )
        return value


class MeetingComponentSerializer(CreateMeetingComponentSerializer):
    is_valid = serializers.BooleanField(read_only=True)
    instance: MeetingComponent

    class Meta(CreateMeetingComponentSerializer.Meta):
        read_only_fields = [
            "component_name",
            "meeting",
        ] + CreateMeetingComponentSerializer.Meta.read_only_fields

    def validate_settings(self, value):
        schema = self.instance.adapter.schema
        if schema:
            try:
                schema(**value)
            except ValueError as exc:
                # Better than nothing!
                raise ValidationError(str(exc))
        else:
            # No schema, so no values are allowed!
            if value is not None:
                raise ValidationError("Component has no schema, so no settings allowed")
        return value


class VerboseMeetingComponentSerializer(MeetingComponentSerializer):
    schema = serializers.SerializerMethodField()

    def get_schema(self, instance: MeetingComponent):
        if instance.adapter and instance.adapter.schema is not None:
            return instance.adapter.schema.schema()
