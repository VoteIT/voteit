from __future__ import annotations

from typing import Optional
from typing import OrderedDict
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.utils import translation
from django.utils.translation import gettext as _
from pydantic.main import BaseModel
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import JSONField

from voteit.core.utils import get_tagged_hashtags
from voteit.core.utils import get_tagged_userids
from voteit.core.validators import valid_userid

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from django_fsm import Transition


class BaseModelSerializer(serializers.ModelSerializer):
    author_kw = "author"

    def create(self, validated_data):
        validated_data[self.author_kw] = self.get_request_user()
        return super().create(validated_data)

    def get_request_user(self) -> Optional[AbstractUser]:
        # Validate user?
        return self.context["request"].user


class OptionalHyperlinkedIdentityField(serializers.HyperlinkedIdentityField):
    def to_representation(self, value):
        if "request" not in self.context:
            return None
        return super().to_representation(value)


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    organisation_roles = serializers.SerializerMethodField()

    def get_full_name(self, instance: AbstractUser):
        return instance.get_full_name()

    def get_organisation_roles(self, instance: AbstractUser):
        roles = instance.organisation_roles.first()
        return [] if roles is None else roles.assigned

    class Meta:
        model = get_user_model()
        fields = (
            "pk",
            "state",
            "userid",
            "full_name",
            "first_name",
            "last_name",
            "img_url",
            "organisation",
            "organisation_roles",
        )


class UpdateUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = (
            "pk",
            "userid",
        )

    def validate_userid(self, value: str):
        user = self.context["request"].user
        try:
            valid_userid(value)
        # FIXME We may want to change to djangos default exception
        except ValueError as exc:
            raise ValidationError(str(exc))
        if self.Meta.model.objects.filter(~Q(pk=user.pk)).filter(userid=value).exists():
            raise ValidationError("Not unique, try something else")
        return value


class TransitionSerializer(serializers.Serializer):
    transition = serializers.CharField(max_length=20)

    class Meta:
        fields = ("transition",)


class PydanticFieldSerializer(JSONField):
    """Handles Pydantic representations and changes them to a rest friendly format.
    It doesn't force pydantic in any way, if it's not a pydantic model it's handled as JSON.
    Note that it has no knowledge of what schema it should expect.

    The encoder/decoder doesn't use pydantic either
    """

    # FIXME: Doctest isn't working as expected
    # >>> from datetime import datetime
    # >>> class Greeting(BaseModel):
    # ...     msg: str = "Hello"
    # ...     timestamp: datetime = datetime(year=1999, month=12, day=24)
    # >>> Greeting.update_forward_refs()
    #
    # Any other object just passes through since this is not really a validator
    # >>> field = PydanticFieldSerializer()
    # >>> field.to_internal_value({"hello": 1})
    # {'hello': 1}
    #
    # JSON will be handled via pydantic instead
    # >>> result = field.to_internal_value(Greeting(msg="hello"))
    # >>> result["msg"]
    # 'hello'
    # >>> result["timestamp"]
    # datetime.datetime(1999, 12, 24, 0, 0)
    #
    # Empty should be okay too
    # >>> field.to_internal_value(None)
    #
    # Same goes for the other way around - a dict or pydantic model loaded from model field
    # >>> field.to_representation({"hi": "there"})
    # {'hi': 'there'}
    #
    # >>> result = field.to_representation(Greeting(msg="hello"))
    # >>> result["msg"]
    # 'hello'
    # >>> result["timestamp"]
    # datetime.datetime(1999, 12, 24, 0, 0)

    def __init__(self, *args, **kwargs):
        """Defualt to DjangoJSONEncoder since it handles more formats"""
        kwargs.setdefault("encoder", DjangoJSONEncoder)
        super().__init__(*args, **kwargs)

    def to_internal_value(self, data):
        if isinstance(data, BaseModel):
            data = data.dict()
        return super().to_internal_value(data)

    def to_representation(self, value):
        if isinstance(value, BaseModel):
            value = value.dict()
        return super().to_representation(value)


class FSMTransitionSerializer(serializers.Serializer):
    name = serializers.CharField()
    permission = serializers.CharField(required=False)
    source = serializers.CharField(required=False)
    target = serializers.CharField()
    title = serializers.SerializerMethodField()

    def get_title(self, field: Transition):
        # Title might be a lazy gettext, which doesn't work
        return translation.gettext(field.custom.get("title", field.name.title()))


class RichTextSerializerMixin:
    """
    On models with body, tags and mentions, like voteit.core.models.BaseContent

    Beware of this since it overrides the validate method
    """

    partial: bool

    # FIXME: body might contain bad tags. That will be cleaned on save, but do we want to send error messages?
    def validate(self, attrs: OrderedDict):
        """
        We'll use this to populate attrs. Pretty silly but there's not other obvious way?
        """
        if self.partial and "body" not in attrs:
            body = self.instance.body
        else:
            body = attrs.get("body", "")
        body_tags = get_tagged_hashtags(body)
        body_mentions = get_tagged_userids(body)
        if self.partial and "tags" not in attrs:
            tags = self.instance.tags and set(self.instance.tags) or set()
        else:
            tags = set(attrs.get("tags", []))
        tags.update(body_tags)
        attrs["tags"] = sorted(tags)
        User = get_user_model()
        if self.partial and "mentions" not in attrs:
            mentions = set(self.instance.mentions.all().values_list("pk", flat=True))
        else:
            mentions = set(
                map(
                    lambda x: isinstance(x, User) and x.pk or x,
                    attrs.get("mentions", []),
                )
            )
        # Validate in 2 steps so we know where things went wrong
        combined_mentions = mentions | body_mentions
        # FIXME: Probably check participants instead...?
        found_users = set(
            User.objects.filter(pk__in=combined_mentions).values_list("pk", flat=True)
        )
        invalid = combined_mentions - found_users
        if invalid:
            msg = _("You can only pick existing users")
            if invalid & mentions:
                raise ValidationError({"mentions": msg})
            else:
                raise ValidationError({"body": msg})
        attrs["mentions"] = combined_mentions
        return super().validate(attrs)
