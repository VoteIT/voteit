from rest_framework import serializers
from voteit.reactions.models import ReactionButton, Reaction


class ButtonDetailSerializer(serializers.ModelSerializer):
    # Note: This won't have access to the request, so no url thingies here!

    class Meta:
        model = ReactionButton
        fields = (
            "pk",
            "title",
            "icon",
            "color",
            "order",
            "change_roles",
            "list_roles",
            "active",
        )


class ContentTypeSerializer(serializers.CharField):
    """ Content type to natural key"""

    def to_internal_value(self, data):
        raise NotImplementedError("Shouldn't be used")

    def to_representation(self, value):
        return ".".join(value.natural_key())


class ReactionSerializer(serializers.ModelSerializer):
    content_type = ContentTypeSerializer(max_length=50)

    class Meta:
        model = Reaction
        fields = (
            "pk",
            "content_type",
            "object_id",
            "button",
            "user",
            "agenda_item",
        )
