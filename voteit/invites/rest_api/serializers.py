import re
from logging import getLogger

from django.db import transaction
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from pydantic import ValidationError as PydanticValidationError
from rest_framework import serializers

from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.core.rest_api.utils import _clean_msg
from voteit.core.validators import DuplicateItemsError
from voteit.core.validators import root_validate_roles_and_model
from voteit.invites.exceptions import DataColValidationError
from voteit.invites.models import MeetingInvite
from voteit.invites.utils import get_invite_adapter_registry
from voteit.invites.utils import send_updated_invites
from voteit.meeting.models import Meeting
from voteit.meeting.rest_api.fields import ModeratorMeetingField
from voteit.meeting.roles import ROLE_MODERATOR
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


def mask_half(value: str) -> str:
    """
    Keep the first half of each name part.

    >>> mask_half("Robin")
    'Ro*'
    >>> mask_half("Harms Oredsson")
    'Ha* Ored*'
    >>> mask_half("Anna-Karin")
    'An*-Ka*'
    """
    if not value:
        return value
    return re.sub(r"[^\s-]+", lambda m: m[0][: len(m[0]) // 2] + "*", value)


def can_switch(user, other) -> bool:
    # Same rule as UserView.get_queryset, so switch accepts it.
    return bool(
        user.identity_id and other.is_active and other.identity_id == user.identity_id
    )


class MatchedInviteSerializer(ExternalMeetingInviteSerializer):
    """
    An invite as the person it matches sees it.

    An invite another account used says something about that account, so how
    much it shows depends on whether the requesting user could switch to it.
    ``user_data`` is always masked by the invite adapters.

    Adds ``used_elsewhere``, ``switch_to`` and ``used_by_account``. An account
    the user can switch to also lists its first ``MAX_MEETINGS`` active meetings,
    from ``account_meetings`` in the context, so the user can tell why to switch.
    """

    MAX_MEETINGS = 5

    def to_representation(self, instance: MeetingInvite):
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = request.user if request else None
        used_elsewhere = bool(
            user and instance.used_by_id and instance.used_by_id != user.pk
        )
        can_switch_to = used_elsewhere and can_switch(user, instance.used_by)
        user_data = instance.user_data
        used_by_account = None
        if used_elsewhere:
            other = instance.used_by
            if can_switch_to:
                meetings = self.context.get("account_meetings", {}).get(other.pk, [])
                used_by_account = {
                    "pk": other.pk,
                    "first_name": other.first_name,
                    "last_name": other.last_name,
                    "userid": other.userid,
                    "last_login": other.last_login,
                    "meetings": meetings[: self.MAX_MEETINGS],
                    "meeting_count": len(meetings),
                }
            else:
                used_by_account = {
                    "pk": other.pk,
                    "first_name": mask_half(other.first_name),
                    "last_name": mask_half(other.last_name),
                    "last_login": other.last_login,
                }
                matched = self.context.get("matched_data") or {}
                user_data = {
                    k: v for k, v in user_data.items() if v in matched.get(k, ())
                }
        data["user_data"] = get_invite_adapter_registry().get_masked_user_data(
            user_data
        )
        data["used_elsewhere"] = used_elsewhere
        data["switch_to"] = instance.used_by_id if can_switch_to else None
        data["used_by_account"] = used_by_account
        return data


def _datacol_message(err: DataColValidationError) -> str:
    """
    Render a DataColValidationError for the user. Checks that can explain
    themselves set ``message``; the rest only know which rows went wrong.
    """
    if err.message:
        return str(err.message)
    row_str = ", ".join(str(r) for r in err.rows)
    return str(
        _("Invalid %(column)s value at row(s): %(rows)s")
        % {"column": err.name, "rows": row_str}
    )


def _pydantic_to_user_messages(exc: PydanticValidationError) -> list[str]:
    """
    Extract readable error strings from a pydantic ValidationError,
    discarding the technical wrapper ("1 validation error for …\nfield\n  …").
    """
    messages = []
    for e in exc.errors():
        # pydantic v2 reports every ValueError as type "value_error" but hands
        # back the original exception in ctx, so branch on the class rather
        # than on the v1-style dotted error type.
        err = e.get("ctx", {}).get("error")
        if isinstance(err, DataColValidationError):
            messages.append(_datacol_message(err))
        elif isinstance(err, DuplicateItemsError):
            messages.append(_("The file contains duplicate rows"))
        else:
            messages.append(_clean_msg(e["msg"]))
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
                {
                    "roles": _(
                        "Your action would downgrade permissions for some moderators. "
                        "Handle moderators via participants tab instead. "
                        "Related to userID(s): %(userids)s"
                    )
                    % {"userids": userids}
                }
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
                {"file": _("The file contains no data rows")}
            )
        columns, rows, roles_per_row = extract_roles_per_row(columns, rows)
        try:
            with schema_context(limit=5000):
                validated = RowColInvitesBaseSchema(columns=columns, rows=rows)
        except PydanticValidationError as exc:
            raise serializers.ValidationError({"file": _pydantic_to_user_messages(exc)})
        except Exception as exc:
            raise serializers.ValidationError({"file": str(exc)})
        try:
            get_invite_adapter_registry().check_conflicting_roles(
                validated.columns, validated.rows, roles_per_row
            )
        except ValueError as exc:
            raise serializers.ValidationError({"file": [str(exc)]})
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
        k
        for k in reg
        if k not in reg.user_data_keys and any(k in item for item in items)
    ]
    return ud_keys + ann_keys


class InviteCreateSerializer(serializers.Serializer):
    meeting = ModeratorMeetingField()
    roles = serializers.ListField(child=serializers.CharField(), min_length=1)
    data = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField(allow_blank=True)),
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
            if not item or all(not val.strip() for val in item.values()):
                continue
            if not any(k in reg.user_data_keys for k in item):
                raise serializers.ValidationError(
                    _("Item %(item_no)s has no identity field (e.g. email).")
                    % {"item_no": i + 1}
                )
            normalised_item = {}
            for key, val in item.items():
                if key not in reg:
                    raise serializers.ValidationError(
                        _("Item %(item_no)s: '%(key)s' is not a valid field.")
                        % {"item_no": i + 1, "key": key}
                    )
                if key in reg.user_data_keys:
                    try:
                        schema_data = reg[key].schema(**{key: val})
                        normalised_item[key] = getattr(schema_data, key)
                    except (ValueError, TypeError) as e:
                        raise serializers.ValidationError(
                            _(
                                "Item %(item_no)s: invalid value for '%(key)s': %(error)s"
                            )
                            % {"item_no": i + 1, "key": key, "error": e}
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
            try:
                reg.preflight(all_keys, col_rows)
                # After preflight, so normalised values are compared
                reg.check_conflicting_annotations(all_keys, col_rows)
            except DataColValidationError as exc:
                raise serializers.ValidationError(_datacol_message(exc)) from exc
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
                reg.run_validators(
                    columns=all_keys, rows=col_rows, meeting=attrs["meeting"]
                )
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
            newly_annotated_pks: set[int] = set()
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
                        newly_annotated_pks.update(ann_result.newly_annotated_invites)
                if newly_annotated_pks:
                    send_updated_invites(
                        meeting,
                        meeting.invites.filter(pk__in=newly_annotated_pks),
                        annotate=True,
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
        if MeetingInvite.objects.filter(id__in=invites, meeting=meeting).count() != len(
            invites
        ):
            raise serializers.ValidationError(
                {"invites": "Invites don't match meeting."}
            )
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
