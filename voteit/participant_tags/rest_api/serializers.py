from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from voteit.participant_tags.components import tag_format
from voteit.participant_tags.models import ParticipantTags
from voteit.participant_tags.utils import get_adapted_from_ns

if TYPE_CHECKING:
    pass


def tag_chars_validator(value: str):
    if not tag_format.match(value):
        raise ValidationError(f"{value} is not a valid tag.")


class SetTagsSerializer(serializers.Serializer):
    tags = serializers.DictField()

    def validate_tags(self, value):
        # Initial validation, only tag format
        for tags in value.values():
            if isinstance(tags, str):
                tag_chars_validator(tags)
            for tag in tags:
                tag_chars_validator(tag)
        # Proper validation
        meeting = self.context["meeting"]
        for ns, ns_value in value.items():
            if adapted := get_adapted_from_ns(meeting, ns):
                settings = adapted.component.settings
                if settings.many:
                    if not isinstance(ns_value, list) or not ns_value:
                        raise ValidationError(
                            f"Value for namespace {ns} must be a list of stings"
                        )
                    for tag in ns_value:
                        if tag not in settings.tags:
                            raise ValidationError(
                                f"{tag} is not a valid tag for namespace {ns}"
                            )
                else:
                    if not isinstance(ns_value, str):
                        raise ValidationError(
                            f"Value for namespace {ns} must be a single string"
                        )
                    if ns_value not in settings.tags:
                        raise ValidationError(
                            f"{ns_value} is not a valid tag for namespace {ns}"
                        )
            else:
                raise ValidationError(f"No tag namespace '{ns}'")
        return value

    def update(self, instance, validated_data):
        """
        This serializer only adjusts the tags field, so we don't need to care about m2m etc
        """
        # raise_errors_on_nested_writes('update', self, validated_data)
        if set(validated_data) != {"tags"}:  # pragma: no coverage
            raise Exception("Validator must only be used for tags")
        changed = False
        for ns, set_tags in validated_data["tags"].items():
            if set_tags != self.instance.tags.get(ns):
                self.instance.tags[ns] = set_tags
                changed = True
        if changed:
            self.instance.save()
        return instance


class DeleteNamespaceSerializer(serializers.Serializer):
    ns = serializers.ListSerializer(child=serializers.CharField())


class TagsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParticipantTags
        read_only_fields = ["pk", "meeting", "user"]
        fields = read_only_fields + [
            "tags",
        ]
