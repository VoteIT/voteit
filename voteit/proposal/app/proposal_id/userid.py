from __future__ import annotations

import itertools
from typing import Optional

from django.utils.text import slugify
from voteit.proposal.abcs import ProposalIDPolicy
from voteit.proposal.registries import proposal_id_registry
from voteit.proposal.models import Proposal

__all__ = ("UseridPID",)


@proposal_id_registry
class UseridPID(ProposalIDPolicy):
    name = "userid"

    def __call__(self, proposal: Proposal) -> Optional[str]:
        if proposal.meeting is None or proposal.author is None:
            return None

        if proposal.meeting_group:
            base_suggestion = proposal.meeting_group.groupid
        elif proposal.author.userid:
            base_suggestion = proposal.author.userid
        else:
            base_suggestion = slugify(proposal.author.get_full_name())

        if base_suggestion:
            meeting_proposals = Proposal.objects.filter(
                agenda_item__meeting=proposal.meeting
            )
            matching_prop_ids = meeting_proposals.filter(
                prop_id__startswith=base_suggestion
            ).values_list('prop_id', flat=True)
            if matching_prop_ids:
                num_part = max(int(prop_id.rsplit("-", 1)[-1]) for prop_id in matching_prop_ids)
            else:
                num_part = 0
            for i in itertools.count(num_part + 1):
                suggestion = f"{base_suggestion}-{i}"
                if not meeting_proposals.filter(prop_id=suggestion).exists():
                    return suggestion
