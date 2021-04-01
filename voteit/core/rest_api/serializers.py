from __future__ import annotations

from typing import Optional
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from pydantic.main import BaseModel
from requests_oauthlib import OAuth2Session
from rest_framework import serializers
from rest_framework.fields import JSONField
from voteit.core.models import OAuth2Provider
from voteit.core.schemas import OAuthStateSchema

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class BaseModelSerializer(serializers.ModelSerializer):
    author_kw = "author"

    def create(self, validated_data):
        ModelClass = self.Meta.model
        validated_data[self.author_kw] = self.get_request_user()
        return ModelClass.objects.create(**validated_data)

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

    def get_full_name(self, instance: AbstractUser):
        return instance.get_full_name()

    class Meta:
        model = get_user_model()
        fields = (
            "pk",
            "username",
            "full_name",
            "first_name",
            "last_name",
        )


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
        """ Defualt to DjangoJSONEncoder since it handles more formats"""
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


class BeginProviderAuthSerializer(serializers.ModelSerializer):
    begin_url = serializers.SerializerMethodField()

    class Meta:
        model = OAuth2Provider
        fields = ["pk", "begin_url", "title", "provider_id"]

    def get_begin_url(self, instance: OAuth2Provider):
        # Get scopes from organisation or provider?
        request = self.context["request"]
        # Note: This is not for security, only to make sure a cookie has been set for the same domain
        # the user will be returned to :)
        redirect_host = urlparse(instance.redirect_url).netloc
        if redirect_host != request.META["HTTP_HOST"]:
            raise serializers.ValidationError(
                "host in redirect_url and request host doesn't match, login would never work. Host must be: %s"
                % redirect_host,
            )
        auth_session = OAuth2Session(
            client_id=instance.client_id,
            scope=instance.scopes,
            redirect_uri=instance.redirect_url,
        )
        authorization_url, state = auth_session.authorization_url(
            instance.auth_url,
            approval_prompt="auto",
        )
        # Only local path for "next" - add domain later
        state_data = OAuthStateSchema(
            provider_pk=instance.pk, next=request.GET.get("next", "/"), state=state
        )
        request.session["oauth_state"] = state_data.dict()
        # request.session.save()
        return authorization_url


class ProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = OAuth2Provider
        fields = ["pk", "title", "organisation", "provider_id"]
