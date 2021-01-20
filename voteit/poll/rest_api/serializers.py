from typing import Sequence

from django.db import transaction
from rest_framework import serializers
from voteit.poll import models


__all__ = ("PollListSerializer", "PollDetailSerializer")

from voteit.poll.registries import poll_methods


# This is a big hackish atm
# TODO Get valid poll methods for meeting
from voteit.proposal.workflows import ProposalWf


class PollMethodField(serializers.ChoiceField):
    """ Get poll methods options """

    def __init__(self, **kwargs):
        super().__init__((), **kwargs)

    def _get_grouped_choices(self):
        return {k: m.title for k, m in poll_methods.items()}

    def _set_grouped_choices(self, choices):
        pass

    grouped_choices = property(_get_grouped_choices, _set_grouped_choices)


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
        fields = "url", "pk", "title", "meeting", "agenda_item", "state", "method_name", "voted", "total"


class PollDetailSerializer(PollListSerializer):
    # Note: This won't have access to the request object, so no url things here!
    class Meta(PollListSerializer.Meta):
        fields = "pk", "title", "meeting", "agenda_item", "state", "method_name", "voted", "total"
        read_only_fields = "state", "voted", "total"


class PollCreateSerializer(serializers.ModelSerializer):
    _proposals: Sequence
    method = PollMethodField(write_only=True)
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
        method_model = poll_methods.get(validated_data.get("method"))
        validated_data["method"] = method_model.objects.create()
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
        fields = "agenda_item", "method", "proposal_pks", "start"
        extra_kwargs = {"agenda_item": {"required": True}}
