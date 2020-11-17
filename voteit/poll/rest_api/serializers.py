from rest_framework import serializers
from voteit.poll import models


__all__ = ("PollListSerializer", "PollDetailSerializer")


class PollListSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Poll
        fields = "url", "pk", "agenda_item", "title", "state"
        read_only_fields = ("state",)


class PollDetailSerializer(serializers.ModelSerializer):
    # Note: This won't have access to the request object, so no url things here!
    class Meta:
        model = models.Poll
        fields = "pk", "title", "agenda_item", "state"
