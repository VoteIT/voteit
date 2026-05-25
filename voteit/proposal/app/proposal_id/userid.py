from __future__ import annotations

import re

from django.utils.text import slugify

from voteit.core.models import User as UserType
from voteit.meeting.models import MeetingGroup
from voteit.proposal.abcs import ProposalIDPolicy
from voteit.proposal.models import Proposal
from voteit.proposal.registries import proposal_id_registry

__all__ = ("UseridPID",)


@proposal_id_registry
class UseridPID(ProposalIDPolicy):
    name = "userid"
    EST_MAX_LEN = 45

    def suggestion(
        self,
        author: UserType | None = None,
        meeting_group: MeetingGroup | None = None,
        as_group: bool = False,
        **kwargs,
    ) -> str | None:
        base_suggestion = None
        if meeting_group and as_group:
            base_suggestion = meeting_group.groupid
        elif author is not None:
            if author.userid:
                base_suggestion = author.userid
            else:
                base_suggestion = author.get_full_name()
        base_suggestion = slugify(base_suggestion, allow_unicode=True)
        if base_suggestion:
            return base_suggestion[: self.EST_MAX_LEN]

    def __call__(self, proposal: Proposal) -> str | None:
        if proposal.meeting is None:
            return None
        if base_suggestion := self.suggestion(
            author=proposal.author,
            meeting_group=proposal.meeting_group,
            as_group=proposal.as_group,
        ):
            # Use an exact-prefix regex to avoid "anna" matching "annabel-1".
            # Fetches all matching IDs in one query, finds max in Python, returns
            # base-{max+1}. The UniqueConstraint is the backstop for race conditions.
            pattern = rf"^{re.escape(base_suggestion)}-(\d+)$"
            matching = list(
                Proposal.objects.filter(
                    agenda_item__meeting=proposal.meeting,
                    prop_id__regex=pattern,
                ).values_list("prop_id", flat=True)
            )
            num_part = (
                max(int(re.search(pattern, pid).group(1)) for pid in matching)
                if matching
                else 0
            )
            return f"{base_suggestion}-{num_part + 1}"
