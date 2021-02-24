from typing import Sequence, Type

from django.db import transaction
from rest_framework import serializers
from voteit.core.rest_api.serializers import OptionalHyperlinkedIdentityField

from voteit.poll import models
from voteit.poll.abcs import PollMethod
from voteit.poll.utils import get_poll_method_registry
from voteit.proposal.workflows import ProposalWf


__all__ = (
    "PollListSerializer",
    "PollDetailSerializer",
    "PollCreateSerializer",
    "ElectoralRegisterSerializer",
)


class PollDetailSerializer(serializers.ModelSerializer):
    # Note: This won't have access to the request object, so no url things here!
    serializer_url_field = OptionalHyperlinkedIdentityField

    class Meta:
        model = models.Poll
        read_only_fields = (
            "agenda_item",
            "electoral_register",
            "initial_electoral_register",
            "meeting",
            "method_name",
            "pk",
            "result_data",
            "settings_data",
            "state",
            "proposals",
            "url",
        )
        fields = list(read_only_fields) + [
            "body",
            "title",
        ]


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

    class Meta:
        fields = [
            "voted",
            "total",
        ] + list(PollDetailSerializer.Meta.fields)


class PollCreateSerializer(serializers.ModelSerializer):
    _proposals: Sequence
    proposal_pks = serializers.CharField(max_length=100, write_only=True)
    start = serializers.BooleanField(write_only=True)
    settings = serializers.JSONField(allow_null=True, write_only=True)

    def validate(self, attrs):
        """ Get proposal set and make sure they're all published. """
        agenda_item = attrs.get("agenda_item")
        proposal_pks = attrs.get("proposal_pks").split(",")
        method_name = attrs.get("method_name")
        settings = attrs.get("settings")
        self._proposals = agenda_item.proposals.filter(
            pk__in=proposal_pks, state=ProposalWf.PUBLISHED
        )
        if len(self._proposals) != len(proposal_pks):
            raise serializers.ValidationError(
                {"proposal_pks": "Proposals must be published on Agenda Item"}
            )
        reg = get_poll_method_registry()
        method: Type[PollMethod] = reg.get(method_name)
        if method is None:
            raise serializers.ValidationError(
                {
                    "method_name": f"{method_name} is not a valid poll method. {repr(list(reg.keys()))}",
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
        """ Create method object and connect proposals """
        validated_data.pop("proposal_pks")
        start = validated_data.pop("start")

        with transaction.atomic():
            poll = super().create(validated_data)
            poll.proposals.set(self._proposals)
            if start:
                poll.upcoming()
                poll.ongoing()
                poll.save()
            return poll

    class Meta:
        model = models.Poll
        fields = "pk", "agenda_item", "method_name", "proposal_pks", "start", "settings"
        extra_kwargs = {"agenda_item": {"required": True}}
        read_only_fields = ("pk",)


class ElectoralRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ElectoralRegister

        fields = read_only_fields = (
            "pk",
            "voters",
        )
