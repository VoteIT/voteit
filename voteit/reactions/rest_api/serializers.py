from rest_framework import serializers

from voteit.core.utils import get_model_shortname
from voteit.reactions.models import Reaction
from voteit.reactions.models import ReactionButton


class ButtonDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReactionButton
        read_only_fields = ("meeting", "flag_mode")
        fields = list(read_only_fields) + [
            "pk",
            "meeting",
            "title",
            "icon",
            "color",
            "order",
            "change_roles",
            "list_roles",
            "active",
            "allowed_models",
            "target",
            "on_presentation",
            "on_vote",
        ]


class ButtonCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReactionButton
        fields = (
            "title",
            "icon",
            "color",
            "meeting",
            "order",
            "change_roles",
            "list_roles",
            "allowed_models",
            "target",
            "flag_mode",
            "on_presentation",
            "on_vote",
        )


class ContentTypeSerializer(serializers.CharField):
    """
    Content type to natural key
    """

    def to_internal_value(self, data):
        raise NotImplementedError("Shouldn't be used")

    def to_representation(self, value):
        return ".".join(value.natural_key())


class ContentTypeShortnameSerializer(serializers.CharField):
    """
    Content type to model shortname.
    """

    def to_internal_value(self, data):
        raise NotImplementedError("Shouldn't be used")

    def to_representation(self, value):
        klass = value.model_class()
        return get_model_shortname(klass)


class ReactionSerializer(serializers.ModelSerializer):
    content_type = ContentTypeShortnameSerializer(max_length=50)

    class Meta:
        model = Reaction
        fields = read_only_fields = (
            "pk",
            "content_type",
            "object_id",
            "button",
            "user",
            "agenda_item",
        )
