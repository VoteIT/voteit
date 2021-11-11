from __future__ import annotations

from contextlib import suppress
from logging import getLogger
from typing import Optional
from typing import OrderedDict
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import translation
from django.utils.translation import gettext as _
from pydantic.main import BaseModel
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import JSONField
from voteit.core.rest_api.utils import get_identity_data

from voteit.core.utils import get_tagged_hashtags
from voteit.core.utils import get_tagged_userids
from voteit.core.validators import valid_userid

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from django_fsm import Transition
    from voteit.core.models import BaseContent
    from voteit.meeting.models import Meeting
    from voteit.agenda.models import AgendaItem


logger = getLogger(__name__)


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
        read_only_fields = fields


class UpdateUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = (
            "pk",
            "userid",
            "email",
        )

    def validate_userid(self, value: str):
        try:
            valid_userid(value)
        # FIXME We may want to change to djangos default exception
        except ValueError as exc:
            raise ValidationError(str(exc))
        user = self.context["request"].user
        if self.Meta.model.objects.exclude(pk=user.pk).filter(userid=value).exists():
            raise ValidationError("Not unique, try something else")
        return value

    def validate_email(self, value: str):
        user = self.context["request"].user
        if user.email == value:
            return value
        identity_data = get_identity_data(user)
        valid_emails = set(
            [x["data"] for x in identity_data["user_data"] if x["scope"] == "email"]
        )
        if value not in valid_emails:
            raise ValidationError(
                _("Email you specified isn't validated. It must exist on your profile.")
            )
        return value


class TransitionSerializer(serializers.Serializer):
    transition = serializers.CharField(max_length=20)

    class Meta:
        fields = ("transition",)


class PydanticFieldSerializer(JSONField):
    """
    Handles Pydantic representations and changes them to a rest friendly format.
    It doesn't force pydantic in any way, if it's not a pydantic model it's handled as JSON.
    Note that it has no knowledge of what schema it should expect.

    The encoder/decoder doesn't use pydantic either
    >>> from datetime import datetime

    >>> class Greeting(BaseModel):
    ...     msg: str = "Hello"
    ...     timestamp: datetime = datetime(year=1999, month=12, day=24)
    ...

    Any other object just passes through since this is not really a validator
    >>> field = PydanticFieldSerializer()
    >>> field.to_internal_value({"hello": 1})
    {'hello': 1}

    JSON will be handled via pydantic instead
    >>> result = field.to_internal_value(Greeting(msg="hello"))
    >>> result["msg"]
    'hello'
    >>> result["timestamp"]
    datetime.datetime(1999, 12, 24, 0, 0)

    Empty should be okay too
    >>> field.to_internal_value(None)

    Same goes for the other way around - a dict or pydantic model loaded from model field
    >>> field.to_representation({"hi": "there"})
    {'hi': 'there'}

    >>> result = field.to_representation(Greeting(msg="hello"))
    >>> result["msg"]
    'hello'
    >>> result["timestamp"]
    datetime.datetime(1999, 12, 24, 0, 0)
    """

    def __init__(self, *args, **kwargs):
        """Default to DjangoJSONEncoder since it handles more formats"""
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
    instance: BaseContent

    def get_user_queryset(self, attrs: OrderedDict) -> models.QuerySet:
        """
        Figure out which queryset to use depending on what's sent in attrs.
        """
        meeting = attrs.get("meeting", None)
        if isinstance(meeting, models.Model):
            meeting: Meeting
            return meeting.participants
        ai = attrs.get("agenda_item", None)
        if isinstance(ai, models.Model):
            ai: AgendaItem
            return ai.meeting.participants
        # We won't catch errors here. This is kind of the last chance to not "leak" data
        # about users through mentions, so if this doesn't work we need to raise a validation error.
        with suppress(AttributeError, ObjectDoesNotExist):
            return self.instance.meeting.participants
        logger.warning(
            "There's no suitable context to pick up user mentions from. Serializer: %s Data:\n%s",
            self.__class__.__name__,
            attrs,
        )
        User = get_user_model()
        return User.objects.none()

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
        if self.partial and "mentions" not in attrs:
            mentions = set(self.instance.mentions.all().values_list("pk", flat=True))
        else:
            User = get_user_model()
            mentions = set(
                map(
                    lambda x: isinstance(x, User) and x.pk or x,
                    attrs.get("mentions", []),
                )
            )
        # Validate in 2 steps so we know where things went wrong
        combined_mentions = mentions | body_mentions
        user_qs = self.get_user_queryset(attrs)
        found_users_qs = user_qs.filter(pk__in=combined_mentions)
        found_user_pks = set(found_users_qs.values_list("pk", flat=True))
        invalid = combined_mentions - found_user_pks
        if invalid:
            msg = _("You can only pick existing users within this meeting")
            if body_mentions - found_user_pks:
                raise ValidationError({"body": msg})
            raise ValidationError({"mentions": msg})
        attrs["mentions"] = list(found_users_qs)
        return super().validate(attrs)
