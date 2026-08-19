from __future__ import annotations

import logging
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import UniqueConstraint

if TYPE_CHECKING:
    from voteit.core.models import User

logger = logging.getLogger(__name__)

_EXPLICITLY_HANDLED = frozenset(
    {
        ("meeting", "meetingroles", "user"),
        ("organisation", "organisationroles", "user"),
        ("active", "activeuser", "user"),
    }
)


def _unique_groups_for_field(model, field_name):
    """Yield field-name tuples for every unique constraint that includes field_name."""
    for ut in model._meta.unique_together:
        if field_name in ut:
            yield tuple(ut)
    for constraint in model._meta.constraints:
        if isinstance(constraint, UniqueConstraint) and field_name in constraint.fields:
            yield tuple(constraint.fields)


def _is_explicitly_handled(rel) -> bool:
    key = (
        rel.related_model._meta.app_label,
        rel.related_model._meta.model_name,
        rel.field.name,
    )
    return key in _EXPLICITLY_HANDLED


@dataclass
class MergeLog:
    moved: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    merged_roles: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)


class UserMerger:
    def __init__(self, source: User, target: User, dry_run: bool = False):
        self.source = source
        self.target = target
        self.dry_run = dry_run
        self.log = MergeLog()

    def run(self) -> MergeLog:
        self._validate()
        with transaction.atomic(durable=True):
            self._handle_meeting_roles()
            self._handle_organisation_roles()
            self._handle_active_users()
            self._handle_electoral_registers()
            self._handle_generic_fk_relations()
            self._handle_speaker_list_order()
            self._handle_generic_m2m_relations()
            self._deactivate_source()
            if self.dry_run:
                transaction.set_rollback(True)
        return self.log

    def _validate(self) -> None:
        if self.source.pk == self.target.pk:
            raise ValueError("Source and target are the same user")
        if self.source.organisation_id != self.target.organisation_id:
            raise ValueError(
                f"Users belong to different organisations: "
                f"source={self.source.organisation_id}, "
                f"target={self.target.organisation_id}"
            )
        if not self.source.organisation_id:
            raise ValueError("Users must belong to an organisation")
        src_id = self.source.identity_id
        tgt_id = self.target.identity_id
        if not src_id or not tgt_id or src_id != tgt_id:
            raise ValueError(
                f"Users must have the same identity_id to be merged "
                f"(source={src_id!r}, target={tgt_id!r})"
            )

    def _handle_meeting_roles(self) -> None:
        from voteit.meeting.models import MeetingRoles

        for src in MeetingRoles.objects.filter(user=self.source):
            has_target = MeetingRoles.objects.filter(
                user=self.target, context=src.context
            ).exists()
            if not self.dry_run:
                src.context.add_roles(self.target, *src.assigned)
                src.delete()
            if has_target:
                self.log.merged_roles.append(
                    f"MeetingRoles pk={src.pk} (meeting_id={src.context_id}): merged roles into target"
                )
            else:
                self.log.moved.append(
                    f"MeetingRoles pk={src.pk} (meeting_id={src.context_id}) moved"
                )

    def _handle_organisation_roles(self) -> None:
        from voteit.organisation.models import OrganisationRoles

        for src in OrganisationRoles.objects.filter(user=self.source):
            has_target = OrganisationRoles.objects.filter(
                user=self.target, context=src.context
            ).exists()
            if not self.dry_run:
                src.context.add_roles(self.target, *src.assigned)
                src.delete()
            if has_target:
                self.log.merged_roles.append(
                    f"OrganisationRoles pk={src.pk} (org_id={src.context_id}): merged roles into target"
                )
            else:
                self.log.moved.append(
                    f"OrganisationRoles pk={src.pk} (org_id={src.context_id}) moved"
                )

    def _handle_active_users(self) -> None:
        from voteit.active.models import ActiveUser

        qs = ActiveUser.objects.filter(user=self.source)
        count = qs.count()
        if count:
            if not self.dry_run:
                qs.delete()
            self.log.deleted.append(f"ActiveUser: deleted {count} transient record(s)")

    def _handle_electoral_registers(self) -> None:
        from voteit.poll.models import ElectoralRegister

        src_key = str(self.source.pk)
        tgt_key = str(self.target.pk)
        for er in ElectoralRegister.objects.filter(voter_data__has_key=src_key):
            if tgt_key in er.voter_data:
                self.log.skipped.append(
                    f"ElectoralRegister pk={er.pk}: target already in register, source entry left on deactivated user"
                )
            else:
                if not self.dry_run:
                    new_data = dict(er.voter_data)
                    new_data[tgt_key] = new_data.pop(src_key)
                    ElectoralRegister.objects.filter(pk=er.pk).update(
                        voter_data=new_data
                    )
                self.log.moved.append(
                    f"ElectoralRegister pk={er.pk}: voter key moved to target"
                )

    def _has_conflict(self, model, field_name, obj) -> bool:
        for fields in _unique_groups_for_field(model, field_name):
            filter_kwargs = {field_name: self.target}
            for f in fields:
                if f == field_name:
                    continue
                if hasattr(obj, f + "_id"):
                    filter_kwargs[f + "_id"] = getattr(obj, f + "_id")
                else:
                    filter_kwargs[f] = getattr(obj, f)
            if model.objects.filter(**filter_kwargs).exists():
                return True
        return False

    def _handle_generic_fk_relations(self) -> None:
        for rel in self.source.__class__._meta.get_fields():
            if not rel.one_to_many or _is_explicitly_handled(rel):
                continue
            model = rel.related_model
            fname = rel.field.name
            for obj in model.objects.filter(**{fname: self.source}):
                if self._has_conflict(model, fname, obj):
                    self.log.skipped.append(
                        f"{model.__name__}.{fname} pk={obj.pk} skipped: unique conflict"
                    )
                else:
                    if not self.dry_run:
                        model.objects.filter(pk=obj.pk).update(**{fname: self.target})
                    self.log.moved.append(f"{model.__name__}.{fname} pk={obj.pk} moved")

    def _handle_speaker_list_order(self) -> None:
        from voteit.speaker.models import Speaker
        from voteit.speaker.models import SpeakerList

        src_str = str(self.source.pk)
        tgt_str = str(self.target.pk)
        affected_list_ids = list(
            Speaker.objects.filter(user=self.target)
            .values_list("speaker_list_id", flat=True)
            .distinct()
        )
        for sl in SpeakerList.objects.filter(
            pk__in=affected_list_ids, order__contains=src_str
        ):
            new_order = ",".join(
                tgt_str if part.strip() == src_str else part
                for part in sl.order.split(",")
            )
            if new_order != sl.order:
                if not self.dry_run:
                    SpeakerList.objects.filter(pk=sl.pk).update(order=new_order)
                self.log.moved.append(f"SpeakerList pk={sl.pk}: updated order field")

    def _handle_generic_m2m_relations(self) -> None:
        for rel in self.source.__class__._meta.get_fields():
            if not rel.many_to_many or not hasattr(rel, "field"):
                continue
            model = rel.related_model
            fname = rel.field.name
            qs = model.objects.filter(**{fname: self.source})
            count = qs.count()
            if count:
                if not self.dry_run:
                    for obj in qs:
                        m2m = getattr(obj, fname)
                        m2m.add(self.target)
                        m2m.remove(self.source)
                self.log.moved.append(
                    f"{model.__name__}.{fname}: updated {count} object(s)"
                )

    def _deactivate_source(self) -> None:
        if not self.dry_run:
            self.source.is_active = False
            self.source.save(update_fields=["is_active"])
        self.log.moved.append(
            f"Source user pk={self.source.pk} deactivated (is_active=False)"
        )
