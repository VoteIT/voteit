from rest_framework import serializers
from voteit.poll import models


__all__ = ("PollListSerializer", "PollDetailSerializer")


class PollListSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Poll
        fields = "url", "pk", "title", "meeting", "agenda_item", "state"
        read_only_fields = ("state",)


class PollDetailSerializer(serializers.ModelSerializer):
    voted = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()

    def get_total(self, instance):
        if instance.electoral_register:
            return instance.method.poll.electoral_register.voters.count()
        return 0

    def get_voted(self, instance):
        return instance.method.vote_set.count()

    # Note: This won't have access to the request object, so no url things here!
    class Meta:
        model = models.Poll
        fields = "pk", "title", "meeting", "agenda_item", "state", "voted", "total"
        read_only_fields = "state",
