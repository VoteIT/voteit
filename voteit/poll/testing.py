from __future__ import annotations
from typing import TYPE_CHECKING

from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.abcs import VoteTransferPolicy
from voteit.poll.app.er_policies.auto_before_poll import AutoBeforePoll

if TYPE_CHECKING:
    from voteit.core.models import User
    from voteit.poll.models import VoteTransfer
    from voteit.poll.models import Poll

# Remember to patch dict first during testing
# @patch.dict(
#    vote_transfer_policies,
#    {UnrestrictedVoteTransferPolicy.name: UnrestrictedVoteTransferPolicy},
# )
# @patch.dict(
#    er_policy,
#    {UnrestrictedVoteTransferER.name: UnrestrictedVoteTransferER},
# )
# class SomeTest(...)


class UnrestrictedVoteTransferPolicy(VoteTransferPolicy):
    """ """

    name = "unrestricted"

    def check(self, source: User, target: User, modifying: VoteTransfer | None = None):
        pass


class UnrestrictedVoteTransferER(AutoBeforePoll):
    """
    For testing
    """

    name = "unrestricted"
    handles_vote_weight = False
    group_votes_active = False
    allow_trigger = True
    handles_active_check = False
    handles_delegate_to = False
    vote_transfer_policy = UnrestrictedVoteTransferPolicy.name

    def get_voters(self, **kwargs) -> dict[int, int]:
        voters = set(self.meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER))
        for vt in self.meeting.vote_transfers.filter(source_id__in=voters):
            voters.add(vt.target_id)
            voters.remove(vt.source_id)
        return {x: 1 for x in voters}

    def pre_apply(self, poll: Poll):
        self.create_er()  # Won't trigger unless needed
