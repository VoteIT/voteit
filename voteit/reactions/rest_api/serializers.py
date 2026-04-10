from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from voteit.core.rest_api.fields import RolesField
from voteit.core.rest_api.utils import validate_model_add
from voteit.core.utils import get_model_shortname
from voteit.reactions.models import Reaction
from voteit.reactions.models import ReactionButton


class ButtonCreateSerializer(serializers.ModelSerializer):
    change_roles = RolesField(required=False)
    list_roles = RolesField(required=False)

    class Meta:
        model = ReactionButton
        read_only_fields = [
            "pk",
        ]
        fields = read_only_fields + [
            "active",
            "title",
            "description",
            "icon",
            "color",
            "meeting",
            "order",
            "change_roles",
            "list_roles",
            "allowed_models",
            "target",
            "flag_mode",
            "vote_template",
            "on_presentation",
            "on_vote",
        ]

    def validate_meeting(self, value):
        validate_model_add(self, ReactionButton, value)
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        query = {}
        for fname in ("color", "icon", "title"):
            query[f"{fname}__iexact"] = attrs.get(
                fname, getattr(self.instance, fname, "")
            )
        meeting = attrs.get("meeting", getattr(self.instance, "meeting", None))
        btn_qs = meeting.reaction_buttons.filter(**query)
        if self.instance:
            btn_qs = btn_qs.exclude(pk=self.instance.pk)
        if btn_qs.exists():
            raise ValidationError(
                {"title": "Duplicate title, change at least color or icon."}
            )
        return attrs


class ButtonDetailSerializer(ButtonCreateSerializer):
    class Meta(ButtonCreateSerializer.Meta):
        read_only_fields = ("meeting", "flag_mode")


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
