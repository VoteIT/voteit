from __future__ import annotations

from typing import OrderedDict

from rest_framework import serializers

from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.core.rest_api.serializers import RichTextSerializerMixin
from voteit.core.rest_api.validators import ValidateGroupAIContext
from voteit.discussion import models


__all__ = ("DiscussionPostDetailSerializer", "DiscussionPostCreateSerializer")


class DiscussionPostDetailSerializer(RichTextSerializerMixin, BaseModelSerializer):
    # Note: This won't have access to the request, so no url thingies here!
    class Meta:
        model = models.DiscussionPost
        read_only_fields = [
            "agenda_item",
            "created",
            "pk",
        ]
        fields = read_only_fields + [
            "author",
            "body",
            "meeting_group",
            "tags",
        ]


class DiscussionPostCreateSerializer(RichTextSerializerMixin, BaseModelSerializer):
    class Meta:
        model = models.DiscussionPost
        read_only_fields = [
            "created",
            "pk",
        ]
        fields = read_only_fields + [
            "agenda_item",
            "author",
            "body",
            "meeting_group",
            "tags",
        ]
        validators = (ValidateGroupAIContext(),)
