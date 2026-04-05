from __future__ import annotations

from itertools import chain

from rest_framework import serializers

from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.core.rest_api.serializers import ExportBaseSerializerMixin
from voteit.core.rest_api.serializers import RichTextSerializerMixin
from voteit.core.rest_api.utils import validate_model_add
from voteit.core.rest_api.validators import ValidateGroupAIContext
from voteit.discussion import models


__all__ = (
    "DiscussionPostDetailSerializer",
    "DiscussionPostCreateSerializer",
)

from voteit.discussion.models import DiscussionPost


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
            "as_group",
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
            "as_group",
        ]
        validators = (ValidateGroupAIContext(),)

    def validate_agenda_item(self, value):
        validate_model_add(self, DiscussionPost, value)

        return value


_export_fields = ["created", "body", "userid", "agenda_item"]
[
    _export_fields.append(f)
    for f in chain(
        ExportBaseSerializerMixin.Meta.fields,
        DiscussionPostDetailSerializer.Meta.fields,
    )
    if f not in _export_fields
]


class DiscussionPostExportSerializer(
    ExportBaseSerializerMixin, serializers.ModelSerializer
):
    class Meta:
        model = models.DiscussionPost
        fields = _export_fields


del _export_fields
