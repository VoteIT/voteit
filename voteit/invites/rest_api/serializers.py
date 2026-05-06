from logging import getLogger

from django.utils.functional import cached_property
from pydantic import ValidationError as PydanticValidationError
from rest_framework import serializers

from voteit.invites.models import MeetingInvite
from voteit.invites.utils import get_invite_adapter_registry
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.meeting import roles
from voteit.meeting.models import Meeting
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
