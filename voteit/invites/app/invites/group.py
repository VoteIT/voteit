from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _
from pydantic import constr
from pydantic.main import BaseModel
from typing import ItemsView

from voteit.invites.abcs import AnnotationDataAdapter
from voteit.invites.registries import invite_adapter_registry
from voteit.invites.schemas import AnnotationResultSchema
from voteit.meeting.models import GroupMembership

if TYPE_CHECKING:
    # from typing.collections import ItemsView
    from django.db.models import QuerySet
    from voteit.invites.models import MeetingInvite
    from voteit.invites.registries import InviteAdapterRegistry
    from voteit.meeting.models import Meeting


class GroupSchema(BaseModel):
    group: constr(to_lower=True, strip_whitespace=True, max_length=100)


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

    def accepted(self):
        """
        Take care of role too since it might be in the dataset
        """
        annotations = self.invite.group_annotations.all()
        for gr in annotations:
            gr.meeting_group.memberships.update_or_create(
                user=self.invite.used_by, defaults={"role": gr.group_role}
            )
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
                "The following groupids don't exist: %s" % ",".join(missing)
            )

    @classmethod
    def annotate(
        cls,
        *,
        invites_qs: QuerySet[MeetingInvite],
        columns: list[str],
        # rows: list[list[str]],
        registry: InviteAdapterRegistry,
        annotations_formatted: list[ItemsView[str, str], dict],
        meeting: Meeting,
        **kwargs,
    ):
        """
        Note that this takes care of group roles too
        """
        from voteit.invites.app.invites.grouprole import InviteGroupRole

        role_mapping = {}
        if InviteGroupRole.name in columns:
            role_mapping.update(meeting.group_roles.all().values_list("role_id", "pk"))
        group_mapping = dict(meeting.groups.all().values_list("groupid", "pk"))
        local_data = annotations_formatted.copy()
        for invite in invites_qs:
            user_data_items = invite.user_data.items()
            popthis = []
            for i, row in enumerate(local_data):
                ud_items, data = row
                if ud_items <= user_data_items:
                    popthis.append(i)
                    if meeting_group := data.get(cls.name):
                        mg_id = group_mapping[meeting_group]

                        if role_id := data.get(InviteGroupRole.name):
                            role_pk = role_mapping[role_id]
                        else:
                            role_pk = None
                        # Invite might be accepted!
                        if invite.used_by:
                            GroupMembership.objects.update_or_create(
                                meeting_group_id=mg_id,
                                user=invite.used_by,
                                defaults={"role_id": role_pk},
                            )
                        else:
                            invite.group_annotations.update_or_create(
                                meeting_invite=invite,
                                meeting_group_id=mg_id,
                                defaults={"group_role_id": role_pk},
                            )
            for i in reversed(popthis):
                local_data.pop(i)
        # FIXME: Counts
        return AnnotationResultSchema(name=cls.name)
