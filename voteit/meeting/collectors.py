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

if TYPE_CHECKING:
    from voteit.messaging.state import AppState


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
        # list of their own.
        groups_qs = self.context.groups.all().prefetch_related("delegate_to")
        state.add_batch(
            MeetingGroupChanged, MeetingGroupSerializer(groups_qs, many=True).data
        )
        memberships_qs = GroupMembership.objects.filter(
            meeting_group__meeting=self.context
        )
        state.add_batch(
            GroupMembershipChanged,
            [
                # Inject meeting pk
                {"m": self.context.pk, **item}
                for item in GroupMembershipSerializer(memberships_qs, many=True).data
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
            GroupRoleChanged,
            GroupRoleSerializer(self.context.group_roles.all(), many=True).data,
        )
