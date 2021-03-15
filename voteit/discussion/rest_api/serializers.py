from __future__ import annotations
from rest_framework import serializers

from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.core.rest_api.validators import ValidateGroupAIContext
from voteit.discussion import models


__all__ = ("DiscussionPostDetailSerializer", "DiscussionPostCreateSerializer")


class DiscussionPostDetailSerializer(serializers.ModelSerializer):
    # Note: This won't have access to the request, so no url thingies here!
    class Meta:
        model = models.DiscussionPost
        read_only_fields = [
            "agenda_item",
            "author",
            "created",
            "meeting_group",
            "pk",
            "tags",
        ]
        fields = read_only_fields + [
            "body",
        ]


class DiscussionPostCreateSerializer(BaseModelSerializer):
    class Meta:
        model = models.DiscussionPost
        fields = [
            "body",
            "agenda_item",
            "meeting_group",
        ]
        validators = (ValidateGroupAIContext(),)
