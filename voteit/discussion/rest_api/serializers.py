from rest_framework import serializers
from voteit.discussion import models


__all__ = ("DiscussionPostListSerializer", "DiscussionPostDetailSerializer")


class DiscussionPostListSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.DiscussionPost
        fields = "url", "title", "agenda_item"


class DiscussionPostDetailSerializer(serializers.ModelSerializer):
    # Note: This won't have access to the request, so no url thingies here!
    class Meta:
        model = models.DiscussionPost
        fields = "pk", "title", "body", "agenda_item", "author"
