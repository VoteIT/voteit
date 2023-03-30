from __future__ import annotations

from collections import Counter
from random import Random
from typing import TYPE_CHECKING

from voteit.meeting.roles import ROLE_POTENTIAL_VOTER

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from voteit.meeting.models import MeetingGroup
    from voteit.core.models import User as UserType
    from voteit.meeting.models import Meeting


def calc_group_votes_equal(
    *,
    meeting: Meeting,
    only_users_qs: QuerySet[UserType] | None = None,
    seed: int | None = None,
) -> dict[int, int]:
    """
    This is equal-ish, since votes power is an integer.
    Use random distribution for left-overs.
    """
    counter = Counter()
    groups_qs = meeting.groups.filter(votes__gt=0).prefetch_related("members")
    potential_voters_pks = meeting.get_userids_with_roles(ROLE_POTENTIAL_VOTER)
    for group in groups_qs:
        group: MeetingGroup
        mqs = group.members.filter(pk__in=potential_voters_pks)
        if only_users_qs is not None:
            mqs = mqs & only_users_qs
        user_pks = list(mqs.values_list("pk", flat=True))
        if not user_pks:
            # Avoid div 0
            continue
        full, rest = divmod(group.votes, len(user_pks))
        for pk in user_pks:
            counter[pk] += full
        if rest:
            if seed is None:
                seed = meeting.pk
            rnd = Random(seed)
            rnd.shuffle(user_pks)
            for pk in user_pks:
                counter[pk] += 1
                rest -= 1
                if not rest:
                    break
    return dict(counter)
