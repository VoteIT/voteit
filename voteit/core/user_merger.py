from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from uuid import uuid4

from auditlog.cid import correlation_id
from auditlog.context import auditlog_disabled
from auditlog.registry import auditlog
from django.db import transaction
from django.db.models import UniqueConstraint
from django.db.models.signals import pre_save
from django.dispatch import receiver

if TYPE_CHECKING:
    from voteit.core.models import User

logger = logging.getLogger(__name__)

_EXPLICITLY_HANDLED = frozenset(
    {
        ("meeting", "meetingroles", "user"),
        ("organisation", "organisationroles", "user"),
        ("active", "activeuser", "user"),
        # The admin's change history. What the source did stays on the source.
        # (auditlog's LogEntry.actor has no reverse relation, so it's never walked.)
        ("admin", "logentry", "user"),
    }
)


#: Actor of every auditlog entry written while a merge runs, including the
#: ones role signals write. auditlog's own set_actor() doesn't restore the
#: previous context on exit, so inside a request it would drop the actor the
#: middleware set.
_merge_actor: ContextVar[User | None] = ContextVar("voteit_merge_actor", default=None)


@receiver(pre_save, sender="auditlog.LogEntry", dispatch_uid="voteit_merge_actor")
def _set_merge_actor(instance, **kwargs):
    actor = _merge_actor.get()
    if actor is not None and instance.actor_id is None:
        instance.actor = actor
        instance.actor_email = actor.email


def log_reassignment(obj, field_name: str, old: User, new: User) -> None:
    """
    Auditlog entry for a row moved from one user to another with update(),
    which sends no signals for auditlog to pick up.
    """
    if auditlog_disabled.get() or not auditlog.contains(obj.__class__):
        return
    from auditlog.models import LogEntry

    LogEntry.objects.log_create(
        obj,
        force_log=True,
        action=LogEntry.Action.UPDATE,
        changes={field_name: [str(old.pk), str(new.pk)]},
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


def user_activity_score(user: User) -> int:
    """
    How much this account would lose by being merged away.

    A zero here means nothing of the person's own is on the row, which is what
    makes an automatic merge safe. Anything above zero wants a human.
    """
    from voteit.discussion.models import DiscussionPost
    from voteit.meeting.models import MeetingRoles
    from voteit.poll.models import Vote
    from voteit.proposal.models import Proposal

    return (
        MeetingRoles.objects.filter(user=user).count()
        + Vote.objects.filter(user=user).count()
        + Proposal.objects.filter(author=user).count()
        + DiscussionPost.objects.filter(author=user).count()
    )


def pick_merge_target(users: list[User], session_user: User | None = None) -> User:
    """
    The account the others should be merged into: elevated first, then the one
    with the most activity, the one signed in, and the latest login.

    Used by the admin merge and by the login pipeline alike.
    """
    from voteit.organisation.matching import is_elevated

    def key(user):
        return (
            is_elevated(user),
            user_activity_score(user),
            session_user is not None and user.pk == session_user.pk,
            user.last_login.timestamp() if user.last_login else 0,
        )

    return max(users, key=key)


def crucial_meetings(user: User) -> set[int]:
    """
    Meetings where this account has voted, is in an electoral register, or is
    in a meeting group. Two accounts sharing one of these must not be merged,
    even when nothing collides row by row.
    """
    from voteit.meeting.models import GroupMembership
    from voteit.poll.models import ElectoralRegister
    from voteit.poll.models import Vote

    pks = set(Vote.objects.filter(user=user).values_list("poll__meeting_id", flat=True))
    pks.update(
        GroupMembership.objects.filter(user=user).values_list(
            "meeting_group__meeting_id", flat=True
        )
    )
    pks.update(
        ElectoralRegister.objects.filter(voter_data__has_key=str(user.pk)).values_list(
            "meeting_id", flat=True
        )
    )
    pks.discard(None)
    return pks


def merge_conflicts(users: list[User]) -> set[int]:
    """
    Meetings where more than one of these accounts has crucial data.
    """
    seen: set[int] = set()
    conflicts: set[int] = set()
    for user in users:
        meetings = crucial_meetings(user)
        conflicts |= seen & meetings
        seen |= meetings
    return conflicts


@dataclass
class MergeLog:
    moved: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    merged_roles: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)


class UserMerger:
    def __init__(
        self,
        source: User,
        target: User,
        dry_run: bool = False,
        same_person: bool = False,
        actor: User | None = None,
    ):
        """
        :param actor: who merged, for auditlog. The admin, or the person
            themselves when they merged at login.
        :param same_person: skip the identity_id check, because something else
            has established that these two rows are one person. Only the id
            proxy writes identity_id, so a pair linked through any other
            provider will never match on it -- see ``AccountLinkOffer``, which
            is how that gets established. Never set this from a guess.
        """
        self.source = source
        self.target = target
        self.dry_run = dry_run
        self.same_person = same_person
        self.actor = actor
        #: Correlation id on every auditlog entry of this merge.
        self.cid = f"user-merge-{uuid4().hex}"
        self.log = MergeLog()
        #: GroupMembership pks changed with update(), published after the merge.
        self._changed_memberships: set[int] = set()

    def run(self) -> MergeLog:
        cid_token = correlation_id.set(self.cid)
        actor_token = _merge_actor.set(self.actor)
        try:
            with transaction.atomic(durable=True):
                self._lock()
                self._validate()
                # Before meeting roles: deleting the source's MeetingRoles cascades
                # into its group memberships (meeting.signals.remove_group_memberships).
                self._handle_group_memberships()
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
                else:
                    self._log_merge()
                    self._publish_memberships()
        finally:
            _merge_actor.reset(actor_token)
            correlation_id.reset(cid_token)
        return self.log

    def _log_merge(self) -> None:
        """
        One entry on each account, since nothing else says that a merge
        happened -- the source's own entry only reads as a deactivation.
        Only pks in changes, see voteit.stats.archive.
        """
        if auditlog_disabled.get():
            return
        from auditlog.models import LogEntry

        summary = {
            "source": self.source.pk,
            "target": self.target.pk,
            "moved": len(self.log.moved),
            "merged_roles": len(self.log.merged_roles),
            "skipped": self.log.skipped,
        }
        for user, key, other in (
            (self.target, "merged_from", self.source),
            (self.source, "merged_into", self.target),
        ):
            LogEntry.objects.log_create(
                user,
                force_log=True,
                action=LogEntry.Action.UPDATE,
                changes={key: ["None", str(other.pk)]},
                additional_data={**user.get_additional_data(), "merge": summary},
            )

    def _lock(self) -> None:
        """
        Two merges of the same accounts at once (two logins finishing together)
        could otherwise each deactivate the other's target. The second one waits
        here and then reads the first one's result.
        """
        from voteit.core.models import User

        list(
            User.objects.select_for_update()
            .filter(pk__in=[self.source.pk, self.target.pk])
            .order_by("pk")
        )
        self.source.refresh_from_db()
        self.target.refresh_from_db()

    def _validate(self) -> None:
        if self.source.pk == self.target.pk:
            raise ValueError("Source and target are the same user")
        # An inactive source is fine, it may be a leftover the admin cleans up.
        if not self.target.is_active:
            raise ValueError(f"Target user pk={self.target.pk} is inactive")
        if self.target.removal_requested is not None:
            # Removing it would take the merged votes and login methods along.
            raise ValueError(
                f"Target user pk={self.target.pk} has requested to be removed"
            )
        if self.source.organisation_id != self.target.organisation_id:
            raise ValueError(
                f"Users belong to different organisations: "
                f"source={self.source.organisation_id}, "
                f"target={self.target.organisation_id}"
            )
        if not self.source.organisation_id:
            raise ValueError("Users must belong to an organisation")
        if self.same_person:
            return
        src_id = self.source.identity_id
        tgt_id = self.target.identity_id
        if not src_id or not tgt_id or src_id != tgt_id:
            raise ValueError(
                f"Users must have the same identity_id to be merged "
                f"(source={src_id!r}, target={tgt_id!r}). Pass same_person=True "
                f"if something else established that these are one person."
            )

    def _handle_meeting_roles(self) -> None:
        from voteit.meeting.models import MeetingRoles

        for src in MeetingRoles.objects.filter(user=self.source):
            # Read before delete() clears it
            src_pk = src.pk
            has_target = MeetingRoles.objects.filter(
                user=self.target, context=src.context
            ).exists()
            if not self.dry_run:
                src.context.add_roles(self.target, *src.assigned)
                src.delete()
            if has_target:
                self.log.merged_roles.append(
                    f"MeetingRoles pk={src_pk} (meeting_id={src.context_id}): merged roles into target"
                )
            else:
                self.log.moved.append(
                    f"MeetingRoles pk={src_pk} (meeting_id={src.context_id}) moved"
                )

    def _handle_group_memberships(self) -> None:
        """
        Moved with update(), so role and votes stay and no role signals fire.
        The meeting roles a group role granted move with the MeetingRoles.
        """
        from voteit.meeting.models import GroupMembership

        target_memberships = {
            m.meeting_group_id: m
            for m in GroupMembership.objects.filter(user=self.target)
        }
        for src in GroupMembership.objects.filter(user=self.source):
            if tgt := target_memberships.get(src.meeting_group_id):
                self._combine_memberships(src, tgt)
                continue
            if not self.dry_run:
                GroupMembership.objects.filter(pk=src.pk).update(user=self.target)
                log_reassignment(src, "user", self.source, self.target)
                self._changed_memberships.add(src.pk)
            self.log.moved.append(
                f"GroupMembership pk={src.pk} (meeting_group_id={src.meeting_group_id}) moved"
            )

    def _combine_memberships(self, src, tgt) -> None:
        """
        Both in one group. The source's membership is deleted with its meeting
        roles, so its votes go to the target's or the group's members would
        no longer add up to MeetingGroup.votes. The target keeps its own role.
        """
        changes = {}
        if src.votes:
            changes["votes"] = (tgt.votes or 0) + src.votes
        if tgt.role_id is None and src.role_id is not None:
            changes["role_id"] = src.role_id
        elif src.role_id not in (None, tgt.role_id):
            self.log.skipped.append(
                f"GroupMembership pk={src.pk} (meeting_group_id={src.meeting_group_id}): "
                f"role_id={src.role_id} dropped, target keeps role_id={tgt.role_id}"
            )
        if changes:
            if not self.dry_run:
                type(tgt).objects.filter(pk=tgt.pk).update(**changes)
                for name, value in changes.items():
                    self._log_membership_change(tgt, name, getattr(tgt, name), value)
                self._changed_memberships.add(tgt.pk)
                if src.votes:
                    # Usually deleted with the source's meeting roles, but it may
                    # have none in this meeting. Either way its votes are moved.
                    type(src).objects.filter(pk=src.pk).update(votes=0)
                    self._log_membership_change(src, "votes", src.votes, 0)
                    self._changed_memberships.add(src.pk)
            self.log.merged_roles.append(
                f"GroupMembership pk={src.pk} (meeting_group_id={src.meeting_group_id}): "
                f"merged into pk={tgt.pk} ({', '.join(sorted(changes))})"
            )
        else:
            self.log.skipped.append(
                f"GroupMembership pk={src.pk} (meeting_group_id={src.meeting_group_id}) "
                f"skipped: target already a member, removed with the source's meeting roles"
            )

    def _publish_memberships(self) -> None:
        """
        update() sends no post_save, so clients would keep the old state.
        """
        if not self._changed_memberships:
            return
        from voteit.meeting.models import GroupMembership
        from voteit.meeting.signals import context_changed_publish_to_meeting

        # Refetched: some may have been deleted since, and those got their own message.
        for membership in GroupMembership.objects.filter(
            pk__in=self._changed_memberships
        ).select_related("meeting_group__meeting"):
            context_changed_publish_to_meeting(membership, sender=GroupMembership)

    @staticmethod
    def _log_membership_change(obj, name, old, new) -> None:
        if auditlog_disabled.get() or not auditlog.contains(obj.__class__):
            return
        from auditlog.models import LogEntry

        LogEntry.objects.log_create(
            obj,
            force_log=True,
            action=LogEntry.Action.UPDATE,
            changes={name.removesuffix("_id"): [str(old), str(new)]},
        )

    def _handle_organisation_roles(self) -> None:
        from voteit.organisation.models import OrganisationRoles

        for src in OrganisationRoles.objects.filter(user=self.source):
            # Read before delete() clears it
            src_pk = src.pk
            has_target = OrganisationRoles.objects.filter(
                user=self.target, context=src.context
            ).exists()
            if not self.dry_run:
                src.context.add_roles(self.target, *src.assigned)
                src.delete()
            if has_target:
                self.log.merged_roles.append(
                    f"OrganisationRoles pk={src_pk} (org_id={src.context_id}): merged roles into target"
                )
            else:
                self.log.moved.append(
                    f"OrganisationRoles pk={src_pk} (org_id={src.context_id}) moved"
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
                    log_reassignment(er, "voter", self.source, self.target)
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
                        log_reassignment(obj, fname, self.source, self.target)
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
                    log_reassignment(sl, "speaker", self.source, self.target)
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
