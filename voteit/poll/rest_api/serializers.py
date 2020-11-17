from rest_framework import serializers
from voteit.poll import models


__all__ = ("PollListSerializer", "PollDetailSerializer")


class PollListSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Poll
        fields = "url", "pk", "agenda_item", "title", "state"
        read_only_fields = ("state",)


class PollDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Poll
        fields = "pk", "title", "agenda_item", "state"
