from typing import Sequence

from django.db import transaction
from rest_framework import serializers

from voteit.poll import models
from voteit.proposal.workflows import ProposalWf


__all__ = ("PollListSerializer", "PollDetailSerializer")


class PollListSerializer(serializers.ModelSerializer):
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
        model = models.Poll
        fields = "url", "pk", "title", "meeting", "agenda_item", "state", "method_name", "voted", "total", "result_data"


class PollDetailSerializer(PollListSerializer):
    # Note: This won't have access to the request object, so no url things here!
    class Meta(PollListSerializer.Meta):
        fields = "pk", "title", "meeting", "agenda_item", "state", "method_name", "voted", "total", "result_data"
        read_only_fields = "state", "voted", "total", "result_data",


class PollCreateSerializer(serializers.ModelSerializer):
    _proposals: Sequence
    proposal_pks = serializers.CharField(max_length=100, write_only=True)
    start = serializers.BooleanField(write_only=True)

    def validate(self, attrs):
        """ Get proposal set and make sure they're all published. """
        agenda_item = attrs.get("agenda_item")
        proposal_pks = attrs.get("proposal_pks").split(",")
        self._proposals = agenda_item.proposals.filter(
            pk__in=proposal_pks, state=ProposalWf.PUBLISHED
        )
        if len(self._proposals) != len(proposal_pks):
            raise serializers.ValidationError(
                "Proposals must be published on Agenda Item"
            )
        return super().validate(attrs)

    def create(self, validated_data):
        """ Create method object and connect proposals """
        validated_data.pop("proposal_pks")
        start = validated_data.pop("start")

        with transaction.atomic():
            poll = super().create(validated_data)
            # TODO Move to a signal?
            for proposal in self._proposals:
                proposal.lock_for_vote()
                proposal.save()
            poll.proposals.set(self._proposals)
            if start:
                poll.upcoming()
                poll.ongoing()
                poll.save()
            return poll

    class Meta:
        model = models.Poll
        fields = "agenda_item", "method_name", "proposal_pks", "start"
        extra_kwargs = {"agenda_item": {"required": True}}
