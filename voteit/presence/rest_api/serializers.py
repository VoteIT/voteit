from rest_framework import serializers
from voteit.presence import models


class PresenceDetailSerializer(serializers.ModelSerializer):

    # Note: This won't have access to the request object, so no url things here!
    class Meta:
        model = models.Presence
        fields = "pk", "user", "presence_check", "created"
        read_only_fields = "created",


class PresenceCheckDetailSerializer(serializers.ModelSerializer):
    meeting = serializers.PrimaryKeyRelatedField(source="presence_system.meeting", read_only=True)

    # Note: This won't have access to the request object, so no url things here!
    class Meta:
        model = models.PresenceCheck
        fields = "pk", "state", "presence_system", "meeting"
        read_only_fields = "state",


class PresenceSystemDetailSerializer(serializers.ModelSerializer):

    # Note: This won't have access to the request object, so no url things here!
    class Meta:
        model = models.PresenceSystem
        fields = "pk", "meeting"
        #read_only_fields = "state",
