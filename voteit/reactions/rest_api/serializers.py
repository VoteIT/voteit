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


class ReactionSerializer(serializers.ModelSerializer):
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
