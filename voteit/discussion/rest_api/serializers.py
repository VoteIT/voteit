from rest_framework import serializers
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.discussion import models


__all__ = ("DiscussionPostListSerializer", "DiscussionPostDetailSerializer")


class DiscussionPostListSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.DiscussionPost
        fields = "url", "pk", "title", "agenda_item", "author"


class DiscussionPostDetailSerializer(BaseModelSerializer):
    # Note: This won't have access to the request, so no url thingies here!
    class Meta:
        model = models.DiscussionPost
        fields = "pk", "title", "body", "agenda_item", "author"
