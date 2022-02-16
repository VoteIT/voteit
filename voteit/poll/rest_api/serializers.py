from typing import Type

from django.db import transaction
from rest_framework import serializers

from voteit.core.rest_api.serializers import OptionalHyperlinkedIdentityField
from voteit.core.rest_api.serializers import PydanticFieldSerializer
from voteit.poll import models
from voteit.poll.abcs import PollMethod
from voteit.poll.utils import get_poll_method_registry

__all__ = (
    "ElectoralRegisterSerializer",
    "PollListSerializer",
    "PollDetailSerializer",
    "PollCreateSerializer",
    "VoteSerializer",
)


class PollDetailSerializer(serializers.ModelSerializer):
    serializer_url_field = OptionalHyperlinkedIdentityField
    settings = PydanticFieldSerializer(allow_null=True, required=False)
    result = PydanticFieldSerializer(allow_null=True, required=False)

    class Meta:
        model = models.Poll
        read_only_fields = (
            "agenda_item",
            "body",
            "closed",
            "electoral_register",
            "initial_electoral_register",
            "meeting",
            "method_name",
            "pk",
            "proposals",
            "result",
            "settings",
            "started",
            "state",
            "title",
            "url",
        )
        fields = read_only_fields


class PollListSerializer(PollDetailSerializer):
    voted = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()

    def get_total(self, instance):
        if instance.electoral_register:
            return instance.method.poll.electoral_register.voters.count()
        return 0

    def get_voted(self, instance):
        # FIXME: Seems to be called too soon?
        if instance.method is not None:
            return instance.votes.count()
        return 0

    class Meta(PollDetailSerializer.Meta):
        fields = [
            "voted",
            "total",
        ] + list(PollDetailSerializer.Meta.fields)
        read_only_fields = fields


class PollCreateSerializer(serializers.ModelSerializer):
    start = serializers.BooleanField(write_only=True, required=False, default=False)
    settings = serializers.JSONField(allow_null=True, write_only=True, required=False)

    def validate(self, attrs):
        """
        Run some extended validation.
        """
        agenda_item = attrs.get("agenda_item")
        proposals = set(attrs.get("proposals"))
        method_name = attrs.get("method_name")
        settings = attrs.get("settings")
        if proposals - set(agenda_item.proposals.all()):
            raise serializers.ValidationError(
                {"proposals": "Proposals must be published on Agenda Item"}
            )
        reg = get_poll_method_registry()
        method: Type[PollMethod] = reg.get(method_name)
        if method is None:
            raise serializers.ValidationError(
                {
                    "method_name": f"{method_name} is not a valid poll method. {repr(list(reg.keys()))}",
                }
            )
        if method.historic:
            raise serializers.ValidationError(
                {
                    "method_name": f"{method_name} is a historic method not ment to be used.",
                }
            )
        if settings is not None:
            if method.settings_schema is None:
                raise serializers.ValidationError(
                    {"settings": "Got settings for a poll that doesn't accept settings"}
                )
            try:
                method.settings_schema(**settings)
            except ValueError:
                raise serializers.ValidationError({"settings": "Invalid settings"})
        return super().validate(attrs)

    def create(self, validated_data):
        start = validated_data.pop("start")

        with transaction.atomic():
            poll = super().create(validated_data)
            if start:
                poll.upcoming()
                poll.ongoing()
                poll.save()
        return poll

    class Meta:
        model = models.Poll
        read_only_fields = [
            "closed",
            "electoral_register",
            "initial_electoral_register",
            "pk",
            "started",
            "state",
            "url",
        ]
        fields = read_only_fields + [
            "agenda_item",
            "body",
            "meeting",
            "method_name",
            "proposals",
            "settings",
            "start",
            "title",
        ]
        extra_kwargs = {
            "agenda_item": {"required": True},
            "meeting": {"required": True},
        }


class ElectoralRegisterSerializer(serializers.ModelSerializer):
    serializer_url_field = OptionalHyperlinkedIdentityField

    class Meta:
        model = models.ElectoralRegister

        fields = read_only_fields = (
            "created",
            "pk",
            "voters",
            "url",
        )


class VoteSerializer(serializers.ModelSerializer):
    vote = PydanticFieldSerializer(allow_null=True)

    class Meta:
        model = models.Vote
        fields = read_only_fields = (
            "pk",
            "user",
            "poll",
            "created",
            "changed",
            "abstain",
            "vote",
        )
