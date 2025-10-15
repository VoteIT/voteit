from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError

from voteit.core.rest_api.serializers import OptionalHyperlinkedIdentityField
from voteit.core.rest_api.serializers import PydanticFieldSerializer
from voteit.core.rest_api.utils import drf_do_transition
from voteit.core.rest_api.utils import get_valid_transitions_dict
from voteit.meeting.models import MeetingRoles
from voteit.meeting.rest_api.fields import UserInMeetingContextField
from voteit.meeting.rest_api.fields import UserInSameMeetingsField
from voteit.meeting.rest_api.fields import UserMeetingField
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.poll.abcs import PollMethod
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.poll.models import Vote
from voteit.poll.models import VoteTransfer
from voteit.poll.models import VoterWeight
from voteit.poll.permissions import VoteTransferPermissions
from voteit.poll.utils import get_poll_method_registry

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting

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
    result = serializers.SerializerMethodField()
    abstain_count = serializers.SerializerMethodField()

    class Meta:
        model = Poll
        read_only_fields = (
            "abstain_count",
            "agenda_item",
            "body",
            "closed",
            "electoral_register",
            "initial_electoral_register",
            "withheld_result",
            "meeting",
            "method_name",
            "pk",
            "proposals",
            "p_ord",
            "result",
            "settings",
            "started",
            "state",
            "title",
            "url",
        )
        fields = read_only_fields

    def get_abstain_count(self, instance: Poll) -> int | None:
        if instance.is_finished:
            return instance.abstains

    def get_result(self, instance: Poll):
        if instance.is_finished and (
            self.context.get("show_withheld", False) or not instance.withheld_result
        ):
            return instance.result_data


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
        method: type[PollMethod] = reg.get(method_name)
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
                user = self.context["request"].user
                valid_transitions = get_valid_transitions_dict(poll)
                drf_do_transition(
                    instance=poll,
                    transition_name="ongoing",
                    valid_transitions=valid_transitions,
                    user=user,
                )
                poll.save()
        return poll

    class Meta:
        model = Poll
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
            "withheld_result",
            "meeting",
            "method_name",
            "proposals",
            "settings",
            "start",
            "title",
            "p_ord",
        ]
        extra_kwargs = {
            "agenda_item": {"required": True},
            "meeting": {"required": True},
        }


class ElectoralRegisterSerializer(serializers.ModelSerializer):
    weights = serializers.SerializerMethodField()

    class Meta:
        model = ElectoralRegister
        fields = read_only_fields = (
            "created",
            "pk",
            "meeting",
            "weights",
            "source",
        )

    def get_weights(self, er: ElectoralRegister) -> list[dict[str, int]]:
        results = []
        for user_pk, weight in er.weight_dict.items():
            results.append({"user": user_pk, "weight": weight})
        return results


class VoterExportSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")
    email = serializers.CharField(source="user.email")
    userid = serializers.CharField(source="user.userid")

    class Meta:
        model = VoterWeight
        exclude = ("id", "register", "user")


class VoteSerializer(serializers.ModelSerializer):
    vote = PydanticFieldSerializer(allow_null=True)

    class Meta:
        model = Vote
        fields = read_only_fields = (
            "pk",
            "user",
            "poll",
            "created",
            "changed",
            "abstain",
            "vote",
        )


class VoteTransferSerializer(serializers.ModelSerializer):
    meeting = UserMeetingField()
    source = UserInSameMeetingsField()
    target = UserInSameMeetingsField()

    class Meta:
        model = VoteTransfer
        fields = [
            "pk",
            "meeting",
            "source",
            "target",
        ]

    def validate_meeting(self, value: Meeting):
        if not self.context["request"].user.has_perm(
            VoteTransferPermissions.ADD, value
        ):
            raise PermissionDenied(
                "You lack the required permission to add (assign) vote transfer in this meeting."
            )
        return value

    def validate(self, attrs):
        actor = self.context["request"].user
        meeting = attrs["meeting"]
        source = attrs["source"]
        target = attrs["target"]
        if source == target:
            raise ValidationError({"target": "target is same as source"})
        # Must exist in meeting
        if (
            MeetingRoles.objects.filter(
                user__in=[source, target], context=meeting
            ).count()
            != 2
        ):
            raise ValidationError(
                {"target": "target user isn't in the same meeting as the source user"}
            )
        # validate source
        if actor != source and not meeting.has_roles(actor, ROLE_MODERATOR):
            raise ValidationError(
                {"source": "You can't delegate votes unless you're a moderator"}
            )
        meeting.vote_transfer_policy.check(source, target)
        return attrs


class VoteTransferReassignSerializer(serializers.ModelSerializer):
    target = UserInMeetingContextField()

    class Meta:
        model = VoteTransfer
        read_only_fields = [
            "meeting",
            "source",
            "pk",
        ]
        fields = read_only_fields + [
            "target",
        ]

    def validate(self, attrs):
        target = attrs["target"]
        if self.instance.source == target:
            raise ValidationError("Can't transfer to self")

        self.instance.meeting.vote_transfer_policy.check(
            source=self.instance.source, target=target, modifying=self.instance
        )
        return attrs
