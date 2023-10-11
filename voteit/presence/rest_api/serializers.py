from rest_framework import serializers

from voteit.presence import models


class PresenceDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Presence
        read_only_fields = [
            "created",
            "pk",
            "presence_check",
            "user",
        ]
        fields = read_only_fields


class PresenceCheckCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.PresenceCheck
        read_only_fields = [
            "state",
            "pk",
            "opened",
            "closed",
        ]
        fields = read_only_fields + ["meeting"]


class PresenceCheckDetailSerializer(PresenceCheckCreateSerializer):
    class Meta(PresenceCheckCreateSerializer.Meta):
        read_only_fields = PresenceCheckCreateSerializer.Meta.read_only_fields + [
            "meeting",
        ]
        fields = read_only_fields
