from rest_framework import serializers

from voteit.core.rest_api.serializers import OptionalHyperlinkedIdentityField
from voteit.presence import models


class PresenceDetailSerializer(serializers.ModelSerializer):
    serializer_url_field = OptionalHyperlinkedIdentityField

    class Meta:
        model = models.Presence
        read_only_fields = [
            "created",
            "pk",
            "presence_check",
            "pk",
            "user",
            "url",
        ]
        fields = list(read_only_fields)


class PresenceCheckDetailSerializer(serializers.ModelSerializer):
    meeting = serializers.PrimaryKeyRelatedField(
        source="presence_system.meeting", read_only=True
    )
    # serializer_url_field = OptionalHyperlinkedIdentityField

    class Meta:
        model = models.PresenceCheck
        read_only_fields = [
            "state",
            "meeting",
            "pk",
            "presence_system",
            # "url",
        ]
        fields = list(read_only_fields)


class PresenceCheckCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.PresenceCheck
        fields = ("presence_system",)


class PresenceSystemDetailSerializer(serializers.ModelSerializer):
    # serializer_url_field = OptionalHyperlinkedIdentityField
    # FIXME: "url" doesn't work here...?

    class Meta:
        model = models.PresenceSystem
        read_only_fields = ["meeting", "pk"]
        fields = read_only_fields


class PresenceSystemCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.PresenceSystem
        fields = ("meeting",)
        extra_kwargs = {
            "meeting": {"required": True},
        }
