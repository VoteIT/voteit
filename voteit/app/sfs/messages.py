try:
    from envelope.core.message import ContextAction
except ImportError:
    from envelope.deferred_jobs.message import ContextAction
from envelope.messages.common import Status
from envelope.messages.errors import BadRequestError
from envelope.utils import websocket_send
from voteit.meeting.models import Meeting
from voteit.core.rules import is_not_finished
from voteit.meeting.models import MeetingGroup
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.messaging.decorators import incoming
from voteit.poll.app.er_policies.group_votes_before_poll import GroupVotesBeforePoll
from voteit.poll.schemas import VotersWeightsSchema

try:  # compat
    from voteit.meeting.permissions import MeetingGroupPermissions
    from voteit.meeting.permissions import MeetingPermissions

    PERM_VIEW_MEETING_GROUP = MeetingGroupPermissions.VIEW
    PERM_CHANGE_MEETING = MeetingPermissions.VIEW

except ImportError:
    from voteit.core import PERM

    PERM_VIEW_MEETING_GROUP = MeetingGroup.get_perm(PERM.VIEW)
    PERM_CHANGE_MEETING = Meeting.get_perm(PERM.CHANGE)


DELEGATION_LEADER_ROLE_ID = "leader"


class SFSSetDelegationVotersSchema(VotersWeightsSchema):
    meeting_group: int


@incoming
class SFSSetDelegationVoters(ContextAction):
    name = "sfs.set_delegation_voters"
    permission = PERM_VIEW_MEETING_GROUP
    model = MeetingGroup
    context_schema_attr = "meeting_group"
    schema = SFSSetDelegationVotersSchema
    data: SFSSetDelegationVotersSchema

    def run_job(self):
        self.assert_perm()
        meeting_group: MeetingGroup = self.context
        if not is_not_finished(self.user, meeting_group.meeting):
            raise BadRequestError.from_message(
                self,
                msg="Meeting closed.",
            )
        # Does the group have votes?
        if not meeting_group.votes:
            raise BadRequestError.from_message(
                self,
                msg="This group has no votes.",
            )
        # Correct amount of votes set?
        total_dist_votes = sum(x.weight for x in self.data.weights)
        if total_dist_votes != meeting_group.votes:
            raise BadRequestError.from_message(
                self,
                msg=f"Bad vote sum. You've set {total_dist_votes} but "
                f"the group has {meeting_group.votes} votes.",
            )
        meeting = meeting_group.meeting
        # Correct ER policy?
        if meeting.er_policy_name != GroupVotesBeforePoll.name:
            raise BadRequestError.from_message(
                self,
                msg=f"This message is only valid while using {GroupVotesBeforePoll.name} electoral register policy.",
            )
        # Delegation leader or moderator?
        if not (
            meeting_group.memberships.filter(
                user=self.user, role__role_id=DELEGATION_LEADER_ROLE_ID
            ).exists()
            or self.user.has_perm(PERM_CHANGE_MEETING, meeting)
        ):
            raise BadRequestError.from_message(
                self,
                msg="You're not delegation leader or moderator.",
            )
        # Check that these users are members of the group + potential voters
        user_pks = {x.user for x in self.data.weights}
        group_member_pks = set(meeting_group.members.all().values_list("pk", flat=True))
        non_members = user_pks - group_member_pks
        if non_members:
            raise BadRequestError.from_message(
                self,
                msg=f"The following user PKs aren't members of that group: {', '.join(str(x) for x in non_members)}.",
            )
        potential_voter_user_pks = set(
            meeting.roles.filter(
                user_id__in=user_pks, assigned__contains=ROLE_POTENTIAL_VOTER
            ).values_list("user_id", flat=True)
        )
        non_potential_voters = user_pks - potential_voter_user_pks
        if non_potential_voters:
            raise BadRequestError.from_message(
                self,
                msg=f"The following user PKs aren't potential voters: {', '.join(str(x) for x in non_potential_voters)}.",
            )
        # Clear all users that aren't specified and have votes
        for membership in meeting_group.memberships.filter(
            votes__gt=0, user_id__in=group_member_pks - user_pks
        ):
            membership.votes = None
            membership.save()
        for vw in self.data.weights:
            meeting_group.memberships.update_or_create(
                user_id=vw.user,
                defaults={"votes": vw.weight},
            )
        response = Status.from_message(self)
        websocket_send(response, state=response.SUCCESS)
        return response
