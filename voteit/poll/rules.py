from __future__ import annotations
from typing import TYPE_CHECKING, Union

import rules
from django.contrib.auth.models import User

from voteit.poll.models import Poll
from voteit.poll.workflows import PollWf
from voteit.poll.permissions import PollPermissions, VotePermissions
from voteit.meeting.permissions import MeetingPermissions

if TYPE_CHECKING:
    from voteit.agenda.models import AgendaItem
    from voteit.organisation.models import Organisation
    from voteit.meeting.models import Meeting


@rules.predicate
def is_voter(user: User, poll: Poll):
    return (
        poll.electoral_register is not None
        and poll.electoral_register.voters.filter(pk=user.pk).exists()
    )


# Object permissions
# @rules.predicate
# def can_add_poll(user: User, instance: Union[Meeting, AgendaItem, Organisation]):
#     from voteit.agenda.models import AgendaItem
#     from voteit.organisation.models import Organisation
#     from voteit.organisation.permissions import OrgPermissions
#     from voteit.meeting.models import Meeting
#     if instance is not None:
#         if isinstance(instance, AgendaItem):
#             # We might want to call this method on the agenda item instead and let that decide
#             return user.has_perm(MeetingPermissions.MODERATE, instance.meeting)
#         elif isinstance(instance, Meeting):
#             return user.has_perm(MeetingPermissions.MODERATE, instance)
#         elif isinstance(instance, Organisation):
#             return user.has_perm(OrgPermissions.MANAGE, instance)


# rules.add_perm(PollPermissions.ADD, can_add_poll)


# @rules.predicate
# def can_change_poll(user: User, poll: Poll):
#     pass
#
# @rules.predicate
# def can_delete_poll(user: User, poll: Poll):
#     poll.
#     pass
#
# @rules.predicate
# def can_view_poll(user: User, poll: Poll):
#     pass


@rules.predicate
def can_vote_now(user: User, poll: Poll):
    # FIXME
    return poll.state == PollWf.ONGOING and is_voter(user, poll)
