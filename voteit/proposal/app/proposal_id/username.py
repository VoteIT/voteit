from __future__ import annotations

import itertools
from typing import Optional

from django.utils.text import slugify
from voteit.proposal.abcs import ProposalIDPolicy
from voteit.proposal.registry import proposal_id_registry
from voteit.proposal.models import Proposal

__all__ = ("UsernamePID",)


@proposal_id_registry
class UsernamePID(ProposalIDPolicy):
    name = "username"

    def __call__(self, proposal: Proposal) -> Optional[str]:
        if proposal.meeting is None:
            return None
        if proposal.author is None:
            return None
            # raise ValueError(f"Proposal {proposal.pk} has no author")
        # TODO Switch to slugify(user.nickname or user.get_full_name()) when implemented
        username = slugify(proposal.author.username)
        if username:
            meeting_proposals = Proposal.objects.filter(agenda_item__meeting=proposal.meeting)
            author_proposals = meeting_proposals.filter(author=proposal.author)
            try:
                last_prop = author_proposals.latest("created")
                num_part = int(last_prop.prop_id.rsplit("-", 1)[-1])
            except Proposal.DoesNotExist:
                num_part = 0
            except ValueError:
                num_part = author_proposals.count()
            for i in itertools.count(num_part + 1):
                suggestion = f"{username}-{i}"
                if not meeting_proposals.filter(prop_id=suggestion).exists():
                    return suggestion
