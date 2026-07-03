from __future__ import annotations

from django.db import transaction
from pydantic import ValidationError as PydanticValidationError
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from auditlog.context import set_actor
from django.utils.translation import gettext as _

from voteit.core.rest_api.serializers import OptionalHyperlinkedIdentityField
from voteit.core.rest_api.serializers import PydanticFieldSerializer
from voteit.core.rest_api.utils import pydantic_to_drf_validation_error
from voteit.core.rest_api.utils import validate_model_add
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles
from voteit.meeting.rest_api.fields import UserInMeetingContextField
from voteit.meeting.rest_api.fields import UserInSameMeetingsField
from voteit.meeting.rest_api.fields import ParticipantMeetingField
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.statemachines import MeetingStateMachine
from voteit.poll.abcs import PollMethod
from voteit.poll.app.er_policies.manual import Manual
from voteit.poll.exceptions import MeetingERMissingError
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.poll.models import Vote
from voteit.poll.models import VoteTransfer
from voteit.poll.utils import get_electoral_policy_registry
from voteit.poll.utils import get_poll_method_registry

__all__ = (
    "ElectoralRegisterSerializer",
    "PollListSerializer",
    "PollDetailSerializer",
    "PollCreateSerializer",
    "VoteSerializer",
    "VoteAddSerializer",
)


class PollDetailSerializer(serializers.ModelSerializer):
    serializer_url_field = OptionalHyperlinkedIdentityField
    settings = PydanticFieldSerializer(allow_null=True, required=False)
    result = serializers.SerializerMethodField()
    abstain_count = serializers.SerializerMethodField()

    class Meta:
        model = Poll
        read_only_fields = [
            "abstain_count",
            "agenda_item",
            "closed",
            "electoral_register",
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
            "url",
        ]
        fields = ["title", "body"] + read_only_fields

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
            return len(instance.method.poll.electoral_register.voter_data)
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

    def validate_agenda_item(self, agenda_item):
        validate_model_add(self, Poll, agenda_item)
        return agenda_item

    def create(self, validated_data):
        start = validated_data.pop("start")

        with transaction.atomic():
            poll = super().create(validated_data)
            if start:
                user = self.context["request"].user
                poll.ongoing(user=user)
                poll.save()
        return poll

    class Meta:
        model = Poll
        read_only_fields = [
            "closed",
            "electoral_register",
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


class ActiveModeratorMeetingField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        return Meeting.objects.filter(
            state__in=[
                MeetingStateMachine.upcoming.value,
                MeetingStateMachine.ongoing.value,
            ],
            roles__user=self.context["request"].user,
            roles__assigned__contains=ROLE_MODERATOR,
        )


class TriggerCreateERSerializer(serializers.Serializer):
    meeting = ActiveModeratorMeetingField()

    def validate_meeting(self, value):
        if not value.is_ongoing:
            raise ValidationError(_("Meeting isn't ongoing"))
        validate_model_add(self, ElectoralRegister, value)
        if value.er_policy_name not in get_electoral_policy_registry():
            raise MeetingERMissingError()
        if not value.er_policy.allow_trigger:
            raise ValidationError("Electoral register can't be triggered this way")
        return value

    def create(self, validated_data):
        meeting = validated_data["meeting"]
        latest_er = meeting.latest_er
        with set_actor(self.context["request"].user):
            new_er = meeting.er_policy.create_er()
        created = bool(new_er and latest_er != new_er)
        self._er = new_er if created else None
        self._created = created
        return validated_data


class VoterWeightItemSerializer(serializers.Serializer):
    user = serializers.IntegerField()
    weight = serializers.IntegerField(min_value=1)


class ManualCreateERSerializer(serializers.Serializer):
    meeting = ActiveModeratorMeetingField()
    weights = VoterWeightItemSerializer(many=True)

    def validate_meeting(self, value):
        if not value.is_ongoing:
            raise ValidationError(_("Meeting isn't ongoing"))
        validate_model_add(self, ElectoralRegister, value)
        if (
            value.er_policy_name not in get_electoral_policy_registry()
            or not value.er_policy.allow_manual
        ):
            raise ValidationError(
                "Electoral register can't be manually created for this meeting"
            )
        return value

    def validate(self, data):
        meeting = data["meeting"]
        weights = data["weights"]
        potential_voters = set(meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER))
        invalid = {w["user"] for w in weights if w["user"] not in potential_voters}
        if invalid:
            raise ValidationError(
                {
                    "weights": f"Got the following invalid potential voters (User PKs): {', '.join(str(x) for x in sorted(invalid))}"
                }
            )
        return data

    def create(self, validated_data):
        meeting = validated_data["meeting"]
        weights = validated_data["weights"]
        weight_dict = {w["user"]: w["weight"] for w in weights}
        manual_er = Manual(meeting)
        latest_er = meeting.latest_er
        with set_actor(self.context["request"].user):
            er = manual_er.create_er(weight_dict=weight_dict)
        created = bool(er and er != latest_er)
        self._er = er if created else None
        self._created = created
        return validated_data


class VoterExportSerializer(serializers.Serializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.CharField()
    userid = serializers.CharField()
    weight = serializers.IntegerField()


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


class VoteAddSerializer(serializers.Serializer):
    """
    Casts or updates the requesting user's vote in a poll (upsert - there's no
    separate "change vote" operation). Set ``abstain`` to abstain instead of voting.
    """

    poll = serializers.PrimaryKeyRelatedField(queryset=Poll.objects.all())
    vote = PydanticFieldSerializer(allow_null=True, required=False)
    abstain = serializers.BooleanField(required=False, default=False)

    def validate_poll(self, poll: Poll):
        # Encodes both "poll is ongoing" and "user is in the electoral register"
        validate_model_add(self, Vote, poll)
        return poll

    def validate(self, attrs):
        if attrs.get("abstain"):
            if attrs.get("vote") is not None:
                raise ValidationError(
                    {"vote": _("Can't provide a vote when abstaining.")}
                )
            attrs["vote"] = None
            return attrs
        poll: Poll = attrs["poll"]
        vote_data = attrs.get("vote")
        if not isinstance(vote_data, dict):
            raise ValidationError(
                {"vote": _("Must be an object matching this poll's vote format.")}
            )
        try:
            vote = poll.method.vote_schema(**vote_data)
        except PydanticValidationError as exc:
            raise ValidationError(
                {"vote": pydantic_to_drf_validation_error(exc).detail}
            ) from exc
        try:
            poll.method.validate_vote(vote)
        except ValidationError as exc:
            raise ValidationError({"vote": exc.detail}) from exc
        attrs["vote"] = vote
        return attrs

    def create(self, validated_data):
        poll: Poll = validated_data["poll"]
        user = self.context["request"].user
        vote, created = poll.votes.update_or_create(
            user=user,
            defaults={
                "vote": validated_data["vote"],
                "abstain": validated_data["abstain"],
            },
        )
        self._created = created
        return vote


class VoteTransferSerializer(serializers.ModelSerializer):
    meeting = ParticipantMeetingField()
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
        validate_model_add(self, VoteTransfer, value)
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
