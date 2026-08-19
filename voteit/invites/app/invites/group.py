from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING
from typing import Generator

from django.db.models import Exists
from django.db.models import OuterRef
from django.utils.translation import gettext_lazy as _
from pydantic import StringConstraints
from pydantic.main import BaseModel

from voteit.invites.abcs import AnnotationDataAdapter
from voteit.invites.models import MeetingGroupAnnotation
from voteit.invites.registries import invite_adapter_registry
from voteit.invites.schemas import AnnotationResultSchema
from voteit.meeting.models import GroupMembership
from typing_extensions import Annotated

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from voteit.invites.models import MeetingInvite
    from voteit.invites.registries import InviteAdapterRegistry
    from voteit.meeting.models import Meeting


class GroupSchema(BaseModel):
    group: Annotated[
        str, StringConstraints(to_lower=True, strip_whitespace=True, max_length=100)
    ]


@invite_adapter_registry
class InviteGroup(AnnotationDataAdapter):
    """
    >>> data = [['WooOO'], [' '], ['  Important']]
    >>> InviteGroup.preflight([InviteGroup.name], data)
    >>> data
    [['woooo'], [''], ['important']]
    """

    name = "group"
    schema = GroupSchema
    title = _("GroupID")
    is_clearable = True

    def accepted(self):
        """
        Take care of role too since it might be in the dataset
        """
        annotations = self.invite.group_annotations.all().prefetch_related(
            "meeting_group",
        )
        for gr in annotations:
            # FIXME refactor so it's reusable
            membership = gr.meeting_group.memberships.filter(
                user=self.invite.used_by
            ).first()
            if not membership:
                # Create, will also signal for role so no problem
                GroupMembership.objects.create(
                    user=self.invite.used_by,
                    meeting_group=gr.meeting_group,
                    role_id=gr.group_role_id,
                )
            else:
                if membership.role_id and not gr.group_role_id:
                    # Role removed
                    old_role = membership.role
                    membership.role = None
                    membership.save()
                    membership.signal_role_removed(role=old_role)
                elif not membership.role_id and gr.group_role_id:
                    # Role added
                    membership.role_id = gr.group_role_id
                    membership.save()
                    membership.signal_role_added()
                elif (
                    membership.role_id
                    and gr.group_role_id
                    and membership.role_id != gr.group_role_id
                ):
                    # Changed
                    old_role = membership.role
                    membership.role = None
                    membership.save()
                    membership.signal_role_removed(role=old_role)
                    membership.role_id = gr.group_role_id
                    membership.save()
                    membership.signal_role_added()
        annotations.delete()

    @classmethod
    def validate(
        cls, *, columns: list[str], rows: list[list[str | None | int]], meeting: Meeting
    ):
        values = cls.get_row_values(columns, rows)
        missing = values - set(
            meeting.groups.filter(groupid__in=values).values_list("groupid", flat=True)
        )
        if missing:
            raise ValueError(
                "The following groupids doesn't exist: %s" % ",".join(missing)
            )

    @classmethod
    def annotate(
        cls,
        *,
        invites_qs: QuerySet[MeetingInvite],
        columns: list[str],
        registry: InviteAdapterRegistry,
        annotations_formatted,
        meeting: Meeting,
        **kwargs,
    ):
        """
        Note that this takes care of group roles too.

        Lifecycle:
        - Already-accepted invites: GroupMembership created/updated immediately (per-invite, signals fire).
        - Pending invites: MeetingGroupAnnotation stored and bulk-created (no signals on that model).
          When the invite is later accepted, InviteGroup.accepted() processes those records.
        """
        from voteit.invites.app.invites.grouprole import InviteGroupRole

        role_mapping = {}
        if InviteGroupRole.name in columns:
            role_mapping.update(meeting.group_roles.all().values_list("role_id", "pk"))
        group_mapping = dict(meeting.groups.all().values_list("groupid", "pk"))
        result = AnnotationResultSchema(name=cls.name)

        # Index rows by their identity portion for O(1) invite matching
        rows_by_ud: dict[frozenset, list[dict]] = defaultdict(list)
        for row in annotations_formatted:
            rows_by_ud[frozenset(row.user_data.items())].append(row.row_data)

        pending_invites = []
        for invite in invites_qs:
            invite_ud = frozenset(invite.user_data.items())
            matched_rows = [
                row_data
                for key, row_list in rows_by_ud.items()
                if key <= invite_ud
                for row_data in row_list
            ]
            if not matched_rows:
                continue

            if invite.used_by_id:
                # Already accepted — apply GroupMembership directly (keep per-invite for signals)
                for row_data in matched_rows:
                    if meeting_group := row_data.get(cls.name):
                        mg_id = group_mapping[meeting_group]
                        role_pk = role_mapping.get(row_data.get(InviteGroupRole.name))
                        if GroupMembership.objects.filter(
                            meeting_group_id=mg_id,
                            user_id=invite.used_by_id,
                            role_id=role_pk,
                        ).exists():
                            result.existed += 1
                        else:
                            _, created = GroupMembership.objects.update_or_create(
                                meeting_group_id=mg_id,
                                user=invite.used_by,
                                defaults={"role_id": role_pk},
                            )
                            if created:
                                result.added += 1
                            else:
                                result.changed += 1
            else:
                pending_invites.append((invite, matched_rows))

        # Bulk-handle pending invites — MeetingGroupAnnotation has no signals
        if pending_invites:
            pending_invite_pks = {invite.pk for invite, _ in pending_invites}
            existing = {
                (inv_pk, mg_id): role_pk
                for inv_pk, mg_id, role_pk in MeetingGroupAnnotation.objects.filter(
                    meeting_invite_id__in=pending_invite_pks
                ).values_list("meeting_invite_id", "meeting_group_id", "group_role_id")
            }
            to_upsert = []
            newly_annotated: set[int] = set()
            for invite, matched_rows in pending_invites:
                for row_data in matched_rows:
                    if meeting_group := row_data.get(cls.name):
                        mg_id = group_mapping[meeting_group]
                        role_pk = role_mapping.get(row_data.get(InviteGroupRole.name))
                        lookup_key = (invite.pk, mg_id)
                        if lookup_key in existing:
                            if existing[lookup_key] == role_pk:
                                result.existed += 1
                            else:
                                result.changed += 1
                                to_upsert.append(
                                    MeetingGroupAnnotation(
                                        meeting_invite_id=invite.pk,
                                        meeting_group_id=mg_id,
                                        group_role_id=role_pk,
                                    )
                                )
                        else:
                            result.added += 1
                            newly_annotated.add(invite.pk)
                            to_upsert.append(
                                MeetingGroupAnnotation(
                                    meeting_invite_id=invite.pk,
                                    meeting_group_id=mg_id,
                                    group_role_id=role_pk,
                                )
                            )
            if to_upsert:
                MeetingGroupAnnotation.objects.bulk_create(
                    to_upsert,
                    update_conflicts=True,
                    update_fields=["group_role_id"],
                    unique_fields=["meeting_invite_id", "meeting_group_id"],
                )
            result.newly_annotated_invites = list(newly_annotated)

        return result

    @classmethod
    def prep_invites_qs_for_subscribe(
        cls, invites_qs: QuerySet[MeetingInvite]
    ) -> QuerySet[MeetingInvite]:
        """
        Attach information about annotations on the queryset itself in advance of serialization.
        Information should be passed along to method 'has_annotations' and doesn't need to result
        in anything else than a bool value.
        """
        return invites_qs.annotate(
            **{
                cls.invite_qs_annotation_name: Exists(
                    MeetingGroupAnnotation.objects.filter(meeting_invite=OuterRef("pk"))
                )
            }
        )

    def get_annotations(self) -> Generator[dict]:
        """
        Return any present annotations for a specific invite.
        It should be in the format of a json-ready dict.
        """
        for val in self.invite.group_annotations.values_list(
            "meeting_group", "group_role"
        ):
            yield dict(zip(["meeting_group", "role"], val))

    @classmethod
    def clear(cls, meeting: Meeting):
        annotations_qs = MeetingGroupAnnotation.objects.filter(
            meeting_group__meeting=meeting
        )
        invites_qs = meeting.invites.filter(
            # Do the search with something that isn't lazy, so it doesn't return none when we clear annotations!
            pk__in=set(annotations_qs.values_list("meeting_invite_id", flat=True))
        )
        annotations_qs.delete()
        return invites_qs

    @classmethod
    def clear_for_invites(cls, invite_pks: list[int]) -> int:
        count, _ = MeetingGroupAnnotation.objects.filter(
            meeting_invite_id__in=invite_pks
        ).delete()
        return count
