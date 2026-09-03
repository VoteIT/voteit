from __future__ import annotations

from typing import TYPE_CHECKING

from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.core.messages.role_updates import RolesChanged
from voteit.core.utils import get_model_shortname
from voteit.meeting.messages import GroupMembershipChanged
from voteit.meeting.messages import GroupRoleChanged
from voteit.meeting.messages import MeetingGroupChanged
from voteit.meeting.models import GroupMembership
from voteit.meeting.rest_api.serializers import GroupMembershipSerializer
from voteit.meeting.rest_api.serializers import GroupRoleSerializer
from voteit.meeting.rest_api.serializers import MeetingGroupSerializer
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors
from voteit.messaging.values import wire_values

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from voteit.messaging.state import AppState


def meeting_group_payloads(qs: QuerySet) -> QuerySet:
    """The ``meeting_group.changed`` payload for every group in ``qs``.

    ``.values()`` rather than MeetingGroupSerializer, which is ten plain columns
    and no method fields. The largest meeting in the dev data has 315 groups:
    6.7 ms / 424 kB through the serializer against 1.0 ms / 189 kB here.
    """
    return wire_values(MeetingGroupSerializer, qs)


def group_membership_payloads(qs: QuerySet) -> QuerySet:
    """The ``group_membership.changed`` payload for every membership in ``qs``.

    ``.values()`` rather than GroupMembershipSerializer, five plain columns and
    no method fields. Memberships scale with participants times groups -- 417
    in the largest dev meeting, 8.1 ms / 258 kB against 1.8 ms / 124 kB.
    """
    return wire_values(GroupMembershipSerializer, qs)


def group_role_payloads(qs: QuerySet) -> QuerySet:
    """The ``group_role.changed`` payload for every role in ``qs``.

    ``.values()`` rather than GroupRoleSerializer. ``roles`` is a declared
    RolesField, but it is a ListField of CharFields over an ArrayField column,
    so it renders the same list either way -- which
    ``test_values_matches_the_serializer`` is there to hold.
    """
    return wire_values(GroupRoleSerializer, qs)


@app_state_collectors
class MeetingRoles(AppStateCollector):
    """The subscribing user's own roles in this meeting."""

    name = "meeting.roles"
    channels = (ParticipantsChannel, ModeratorsChannel)
    order = 10

    def collect(self, state: AppState) -> None:
        roles = self.context.get_roles(self.user)
        if roles:
            state.append(
                RolesChanged(
                    payload={
                        "roles": roles,
                        "pk": self.context.pk,
                        "model": get_model_shortname(self.context),
                        "user_pk": self.user.pk,
                    }
                )
            )


@app_state_collectors
class MeetingGroups(AppStateCollector):
    """Meeting groups and who is in them."""

    name = "meeting.groups"
    channels = (ParticipantsChannel, ModeratorsChannel)
    order = 20

    def collect(self, state: AppState) -> None:
        # Members have moved to GroupMembership, so the groups carry no user
        # list of their own. No prefetch on delegate_to: it is a ForeignKey and
        # the serializer renders it with a PrimaryKeyRelatedField, which reads
        # delegate_to_id without ever loading the group -- the prefetch this
        # replaced was a second query that bought nothing.
        groups_qs = self.context.groups.all()
        state.add_batch(MeetingGroupChanged, meeting_group_payloads(groups_qs))
        memberships_qs = GroupMembership.objects.filter(
            meeting_group__meeting=self.context
        )
        state.add_batch(
            GroupMembershipChanged,
            [
                # Inject meeting pk
                {"m": self.context.pk, **item}
                for item in group_membership_payloads(memberships_qs)
            ],
        )


@app_state_collectors
class MeetingGroupRoles(AppStateCollector):
    name = "meeting.group_roles"
    channels = (ParticipantsChannel, ModeratorsChannel)
    order = 20

    def applicable(self) -> bool:
        return self.context.group_roles_active

    def collect(self, state: AppState) -> None:
        state.add_batch(
            GroupRoleChanged, group_role_payloads(self.context.group_roles.all())
        )
