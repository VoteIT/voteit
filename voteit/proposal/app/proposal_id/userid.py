from __future__ import annotations

import itertools
from typing import Optional

from django.utils.text import slugify
from voteit.proposal.abcs import ProposalIDPolicy
from voteit.proposal.registry import proposal_id_registry
from voteit.proposal.models import Proposal

__all__ = ("UseridPID",)


@proposal_id_registry
class UseridPID(ProposalIDPolicy):
    name = "userid"

    def __call__(self, proposal: Proposal) -> Optional[str]:
        if proposal.meeting is None or proposal.author is None:
            return None

        if proposal.author.userid:
            base_suggestion = proposal.author.userid
        else:
            base_suggestion = slugify(proposal.author.get_full_name())

        if base_suggestion:
            meeting_proposals = Proposal.objects.filter(
                agenda_item__meeting=proposal.meeting
            )
            author_proposals = meeting_proposals.filter(author=proposal.author)
            try:
                last_prop = author_proposals.latest("created")
                num_part = int(last_prop.prop_id.rsplit("-", 1)[-1])
            except Proposal.DoesNotExist:
                num_part = 0
            except ValueError:
                num_part = author_proposals.count()
            for i in itertools.count(num_part + 1):
                suggestion = f"{base_suggestion}-{i}"
                if not meeting_proposals.filter(prop_id=suggestion).exists():
                    return suggestion
