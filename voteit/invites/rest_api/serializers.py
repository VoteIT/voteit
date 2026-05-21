from logging import getLogger

from django.db import transaction
from django.utils.functional import cached_property
from rest_framework import serializers

from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.core.validators import root_validate_roles_and_model
from voteit.invites.models import MeetingInvite
from voteit.invites.utils import get_invite_adapter_registry
from voteit.meeting import roles
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.workflows import MeetingWf

logger = getLogger(__name__)


class InviteQuerySerializer(serializers.Serializer):
    scope = serializers.CharField()
    data = serializers.CharField()
    validated = serializers.DateTimeField()

    def validate_scope(self, value):
        if value not in get_invite_adapter_registry():
            # Note: This is since we don't want endpoints do die then there's a missmatch
            # between keywords and scopes. That's okay as long as we don't use this serializer
            # for external endpoints.
            logger.warning("No invite scope %s", value)
        return value


class MeetingInviteSerializer(BaseModelSerializer):
    """
    For read operations
    """

    has_annotations = serializers.SerializerMethodField()
    roles = serializers.ListSerializer(child=serializers.CharField())

    class Meta:
        model = MeetingInvite
        read_only_fields = [
            "meeting",
            "pk",
            "state",
            "used_by",
            "user_data",
            "roles",
            "has_annotations",
        ]
        fields = read_only_fields

    @cached_property
    def registry(self):
        return get_invite_adapter_registry()

    def get_has_annotations(self, instance: MeetingInvite) -> bool:
        """
        If the qs was passed as initial data ("instance") expect an annotated qs, else fetch.
        The odd arguments with both instance and self.instance is due to that.
        """
        return self.registry.has_annotations(
            instance, from_qs=not isinstance(self.instance, MeetingInvite)
        )


class ExternalMeetingInviteSerializer(serializers.ModelSerializer):
    """Used when querying from login service."""

    organisation_host = serializers.SerializerMethodField()
    meeting_title = serializers.SerializerMethodField()
    roles = serializers.ListSerializer(child=serializers.CharField())

    class Meta:
        model = MeetingInvite
        read_only_fields = [
            "created",
            "user_data",
            "meeting",
            "meeting_title",
            "modified",
            "organisation_host",
            "pk",
            "roles",
            "state",
            "used_at",
            "used_by",
        ]
        fields = read_only_fields

    def get_organisation_host(self, instance: MeetingInvite) -> str:
        try:
            return instance.meeting.organisation.host
        except AttributeError:  # pragma: no coverage
            # Only unittests!
            pass

    def get_meeting_title(self, instance: MeetingInvite) -> str:
        return instance.meeting.title


class ModeratorMeetingField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        return Meeting.objects.filter(
            roles__user=self.context["request"].user,
            roles__assigned__contains=roles.ROLE_MODERATOR,
        ).exclude(state__in=MeetingWf.archived_states)


class InviteCreateSerializer(serializers.Serializer):
    meeting = ModeratorMeetingField()
    roles = serializers.ListField(child=serializers.CharField(), min_length=1)
    data = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField()),
        min_length=1,
        max_length=1000,
    )
    dryrun = serializers.BooleanField(default=False)

    def validate_roles(self, v):
        try:
            root_validate_roles_and_model(None, {"model": "meeting", "roles": v})
        except (ValueError, AssertionError) as e:
            raise serializers.ValidationError(str(e)) from e
        return v

    def validate_data(self, v):
        reg = get_invite_adapter_registry()
        normalised = []
        for i, item in enumerate(v):
            if not item:
                raise serializers.ValidationError(f"Item {i + 1} is empty.")
            normalised_item = {}
            for key, val in item.items():
                if key not in reg.user_data_keys:
                    raise serializers.ValidationError(
                        f"Item {i + 1}: '{key}' is not a valid user data type."
                    )
                try:
                    schema_data = reg[key].schema(**{key: val})
                    normalised_item[key] = getattr(schema_data, key)
                except (ValueError, TypeError) as e:
                    raise serializers.ValidationError(
                        f"Item {i + 1}: invalid value for '{key}': {e}"
                    ) from e
            normalised.append(normalised_item)
        # Cross-item intersection check: a single key=value must not appear
        # across items with different total user_data (subset conflict).
        all_items_views = [x.items() for x in normalised]
        checked = []
        for i, item in enumerate(normalised, 1):
            item_view = item.items()
            if item_view in checked:
                continue
            for k, val in item_view:
                partial = {k: val}.items()
                if any(
                    partial <= other for other in all_items_views if other != item_view
                ):
                    raise serializers.ValidationError(
                        f"The value {k}={val} appears in overlapping subsets of user data. "
                        f"Offending item: {i}"
                    )
            checked.append(item_view)
        return normalised

    def validate(self, attrs):
        meeting = attrs["meeting"]
        item_roles = attrs["roles"]
        data = attrs["data"]
        if ROLE_MODERATOR not in item_roles:
            curr_moderator_pks = meeting.roles.filter(
                assigned__contains=ROLE_MODERATOR
            ).values_list("user", flat=True)
            if (
                meeting.invites.find_mixed_user_data(*data)[0]
                .filter(used_by__in=curr_moderator_pks)
                .exists()
            ):
                raise serializers.ValidationError(
                    "This would downgrade roles for an existing moderator."
                )
        return attrs

    def save(self, **kwargs):
        vd = self.validated_data
        meeting = vd["meeting"]
        with transaction.atomic(durable=True):
            result = meeting.invites.create_or_update_mixed(
                data=vd["data"], roles=vd["roles"], meeting=meeting
            )
            if vd["dryrun"]:
                transaction.set_rollback(True)
        return result


class InviteBulkSerializer(serializers.Serializer):
    invites = serializers.ListSerializer(child=serializers.IntegerField())
    meeting = ModeratorMeetingField()

    def validate(self, attrs):
        invites: list[int] = attrs["invites"]
        meeting: Meeting = attrs["meeting"]
        if MeetingInvite.objects.filter(id__in=invites, meeting=meeting).count() != len(
            invites
        ):
            raise serializers.ValidationError(
                {"invites": "Invites don't match meeting."}
            )
        return attrs
