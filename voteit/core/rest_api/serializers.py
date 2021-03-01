from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from pydantic.main import BaseModel
from rest_framework import serializers
from rest_framework.fields import JSONField

UserModel = get_user_model()


class BaseModelSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        ModelClass = self.Meta.model
        return ModelClass.objects.create(
            author=self.context["request"].user, **validated_data
        )


class OptionalHyperlinkedIdentityField(serializers.HyperlinkedIdentityField):
    def to_representation(self, value):
        if "request" not in self.context:
            return None
        return super().to_representation(value)


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    def get_full_name(self, instance: UserModel):
        return instance.get_full_name()

    class Meta:
        model = UserModel
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
