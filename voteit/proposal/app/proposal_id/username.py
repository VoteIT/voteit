from __future__ import annotations

from typing import Optional

from voteit.proposal.abcs import ProposalIDPolicy
from voteit.proposal.registry import proposal_id_registry
from voteit.proposal.models import Proposal

__all__ = ("UsernamePID",)


@proposal_id_registry
class UsernamePID(ProposalIDPolicy):
    name = "username"

    def __call__(self, proposal: Proposal) -> Optional[str]:
        if proposal.agenda_item is None:
            return None
        if proposal.author is None:
            return None
            # raise ValueError(f"Proposal {proposal.pk} has no author")
        username = proposal.author.username
        if username:
            last_prop = (
                Proposal.objects.filter(
                    agenda_item=proposal.agenda_item, author=proposal.author
                )
                .order_by("-created")
                .first()
            )
            if last_prop:
                try:
                    num_part = int(last_prop.prop_id.split("-")[-1])
                except ValueError:
                    num_part = (
                        Proposal.objects.filter(
                            agenda_item=proposal.agenda_item, author=proposal.author
                        ).count()
                        + 1
                    )
            else:
                num_part = 1
            for i in range(num_part, num_part + 20):
                suggestion = f"{username}-{i}"
                if not Proposal.objects.filter(prop_id=suggestion).exists():
                    return suggestion
