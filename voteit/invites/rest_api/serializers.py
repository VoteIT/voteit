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


def _raise_if_conflicting_partials(meeting, items: list[dict]) -> None:
    _existing, conflicting = meeting.invites.find_mixed_user_data(*items)
    if conflicting:
        cols = ", ".join(conflicting.keys())
        raise serializers.ValidationError(
            _(
                "Found existing invites matching only parts of a row. "
                "Check for conflicting data in column(s): %(cols)s"
            )
            % {"cols": cols}
        )


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


def _items_to_columns(items: list[dict], reg) -> list[str]:
    """
    Build an ordered column list from items.
    User-data keys come first (sorted), annotation keys follow in registry registration order
    so that cross-column constraints (e.g. grouprole must follow group) are satisfied.
    """
    ud_keys = sorted({k for item in items for k in item if k in reg.user_data_keys})
    ann_keys = [
        k for k in reg
        if k not in reg.user_data_keys and any(k in item for item in items)
    ]
    return ud_keys + ann_keys


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
            if not any(k in reg.user_data_keys for k in item):
                raise serializers.ValidationError(
                    f"Item {i + 1} has no identity field (e.g. email)."
                )
            normalised_item = {}
            for key, val in item.items():
                if key not in reg:
                    raise serializers.ValidationError(
                        f"Item {i + 1}: '{key}' is not a valid field."
                    )
                if key in reg.user_data_keys:
                    try:
                        schema_data = reg[key].schema(**{key: val})
                        normalised_item[key] = getattr(schema_data, key)
                    except (ValueError, TypeError) as e:
                        raise serializers.ValidationError(
                            f"Item {i + 1}: invalid value for '{key}': {e}"
                        ) from e
                else:
                    normalised_item[key] = val
            normalised.append(normalised_item)
        all_keys = _items_to_columns(normalised, reg)
        try:
            reg.check_column_req(all_keys)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))
        ann_keys = [k for k in all_keys if k not in reg.user_data_keys]
        if ann_keys:
            col_rows = [[item.get(k, "") for k in all_keys] for item in normalised]
            reg.preflight(all_keys, col_rows)
            for item, row in zip(normalised, col_rows):
                for k, cell in zip(all_keys, row):
                    item[k] = cell
        ud_keys = [k for k in all_keys if k in reg.user_data_keys]
        ud_col_rows = [[item.get(k, "") for k in ud_keys] for item in normalised]
        try:
            reg.check_intersections(ud_keys, ud_col_rows)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))
        return normalised

    def validate(self, attrs):
        reg = get_invite_adapter_registry()
        data = attrs["data"]
        all_keys = _items_to_columns(data, reg)
        ann_keys = [k for k in all_keys if k not in reg.user_data_keys]
        if ann_keys:
            col_rows = [[item.get(k, "") for k in all_keys] for item in data]
            try:
                reg.run_validators(columns=all_keys, rows=col_rows, meeting=attrs["meeting"])
            except ValueError as exc:
                raise serializers.ValidationError(str(exc))
        ud_items = [
            {k: v for k, v in item.items() if k in reg.user_data_keys} for item in data
        ]
        _raise_if_conflicting_partials(attrs["meeting"], ud_items)
        _raise_if_moderator_lockout(attrs["meeting"], ud_items, attrs["roles"])
        return attrs

    def save(self, **kwargs):
        vd = self.validated_data
        meeting = vd["meeting"]
        data: list[dict] = vd["data"]
        reg = get_invite_adapter_registry()
        ud_keys = reg.user_data_keys
        ud_items = [{k: v for k, v in item.items() if k in ud_keys} for item in data]
        annotation_results = []
        with transaction.atomic(durable=True):
            invite_result = meeting.invites.create_or_update_mixed(
                data=ud_items, roles=vd["roles"], meeting=meeting
            )
            all_keys = _items_to_columns(data, reg)
            ann_keys = [k for k in all_keys if k not in ud_keys]
            if ann_keys:
                col_rows = [[item.get(k, "") for k in all_keys] for item in data]
                for ann_result in reg.run_annotations(
                    columns=all_keys,
                    rows=col_rows,
                    invites_qs=meeting.invites.all(),
                    meeting=meeting,
                ):
                    if ann_result:
                        annotation_results.append(
                            {
                                "name": ann_result.name,
                                "added": ann_result.added,
                                "changed": ann_result.changed,
                                "existed": ann_result.existed,
                            }
                        )
            if vd["dryrun"]:
                transaction.set_rollback(True)
        return {
            "invites": {
                "added": invite_result.added,
                "changed": invite_result.changed,
                "existed": invite_result.existed,
            },
            "annotations": annotation_results,
            "dryrun": vd["dryrun"],
        }


class InviteClearAnnotationsSerializer(serializers.Serializer):
    meeting = ModeratorMeetingField()
    invites = serializers.ListSerializer(child=serializers.IntegerField(), min_length=1)

    def validate(self, attrs):
        invites = attrs["invites"]
        meeting = attrs["meeting"]
        if MeetingInvite.objects.filter(id__in=invites, meeting=meeting).count() != len(invites):
            raise serializers.ValidationError({"invites": "Invites don't match meeting."})
        return attrs


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
