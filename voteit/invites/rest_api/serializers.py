from logging import getLogger

from django.db import transaction
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from pydantic import ValidationError as PydanticValidationError
from rest_framework import serializers

from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.core.validators import root_validate_roles_and_model
from voteit.invites.models import MeetingInvite
from voteit.invites.utils import get_invite_adapter_registry
from voteit.meeting import roles
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.workflows import MeetingWf
from voteit.invites.rest_api.import_utils import detect_and_parse_file
from voteit.invites.rest_api.import_utils import extract_roles_per_row
from voteit.invites.schemas import RowColInvitesBaseSchema
from voteit.invites.schemas import schema_context

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


def _pydantic_to_user_messages(exc: PydanticValidationError) -> list[str]:
    """
    Extract readable error strings from a Pydantic v1 ValidationError,
    discarding the technical wrapper ("1 validation error for …\nfield\n  …").
    """
    messages = []
    for e in exc.errors():
        error_type = e.get("type", "")
        if error_type == "value_error.datacolvalidation":
            ctx = e.get("ctx", {})
            name = ctx.get("name", "")
            rows = ctx.get("rows", [])
            row_str = ", ".join(str(r) for r in rows)
            messages.append(f"Invalid {name} value at row(s): {row_str}")
        elif error_type == "value_error.list.unique_items":
            messages.append("The file contains duplicate rows")
        else:
            messages.append(e["msg"])
    return messages


def _raise_if_moderator_lockout(meeting, items: list[dict], roles: list[str]) -> None:
    if ROLE_MODERATOR not in roles:
        existing_qs, _conflicting = meeting.invites.find_mixed_user_data(*items)
        curr_moderators = meeting.roles.filter(
            assigned__contains=ROLE_MODERATOR
        ).values_list("user", flat=True)
        at_risk = existing_qs.filter(used_by__in=curr_moderators)
        if at_risk.exists():
            userids = ", ".join(
                x for x in at_risk.values_list("used_by__userid", flat=True) if x
            )
            raise serializers.ValidationError(
                _(
                    "Your action would downgrade permissions for some moderators. "
                    "Handle moderators via participants tab instead. "
                    "Related to userID(s): %(userids)s"
                )
                % {"userids": userids}
            )


class InviteImportSerializer(serializers.Serializer):
    meeting = ModeratorMeetingField()
    file = serializers.FileField()
    dryrun = serializers.BooleanField(default=False)

    def validate(self, data):
        raw = data["file"].read()
        try:
            columns, rows = detect_and_parse_file(raw)
        except ValueError as exc:
            raise serializers.ValidationError({"file": str(exc)})
        if not rows:
            raise serializers.ValidationError(
                {"file": "The file contains no data rows"}
            )
        columns, rows, roles_per_row = extract_roles_per_row(columns, rows)
        try:
            with schema_context(limit=5000):
                validated = RowColInvitesBaseSchema(columns=columns, rows=rows)
        except PydanticValidationError as exc:
            raise serializers.ValidationError({"file": _pydantic_to_user_messages(exc)})
        except Exception as exc:
            raise serializers.ValidationError({"file": str(exc)})
        data["columns"] = validated.columns
        data["rows"] = validated.rows
        data["roles_per_row"] = roles_per_row
        return data


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
        all_keys = sorted({k for item in normalised for k in item})
        col_rows = [[item.get(k, "") for k in all_keys] for item in normalised]
        try:
            reg.check_intersections(all_keys, col_rows)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))
        return normalised

    def validate(self, attrs):
        _raise_if_moderator_lockout(attrs["meeting"], attrs["data"], attrs["roles"])
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
