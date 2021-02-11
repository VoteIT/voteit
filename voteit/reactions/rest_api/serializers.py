from rest_framework import serializers
from voteit.reactions.models import ReactionButton


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
