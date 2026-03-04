from __future__ import annotations

from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from voteit.notes.models import Note


__all__ = (
    "NoteSerializer",
    "CreateNoteSerializer",
)


class NoteSerializer(serializers.ModelSerializer):
    agenda_item = serializers.PrimaryKeyRelatedField(
        source="proposal.agenda_item", read_only=True
    )

    class Meta:
        model = Note
        read_only_fields = [
            "pk",
            "agenda_item",
            "meeting",
            "created",
            "proposal",
            "user",
        ]
        fields = read_only_fields + [
            "body",
            "intent",
        ]


class CreateNoteSerializer(NoteSerializer):
    user = serializers.PrimaryKeyRelatedField(
        read_only=True, required=False, default=serializers.CurrentUserDefault()
    )

    class Meta:
        model = Note
        read_only_fields = [
            "pk",
            "meeting",
            "agenda_item",
            "created",
            "user",
        ]
        fields = read_only_fields + [
            "proposal",
            "body",
            "intent",
        ]
        validators = [
            UniqueTogetherValidator(
                queryset=Note.objects.all(), fields=["user", "proposal"]
            )
        ]

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)
