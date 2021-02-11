from __future__ import annotations
from typing import TYPE_CHECKING, Union

import rules
from django.contrib.auth.models import AbstractUser
from voteit.core.decorators import predicate
from voteit.core.rules import is_not_archived
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.rules import is_moderator
from voteit.reactions.models import ReactionButton
from voteit.reactions.permissions import ReactionButtonPermissions

if TYPE_CHECKING:
    pass


@predicate
def user_can_change_meeting(
    user: AbstractUser, obj: Union[Meeting, ReactionButton]
) -> bool:
    """ Delegate permission check to meeting"""
    meeting = None
    if isinstance(obj, ReactionButton):
        meeting = obj.meeting
    elif isinstance(obj, Meeting):
        meeting = obj
    return user.has_perm(MeetingPermissions.CHANGE, meeting)


@predicate
def user_can_view_meeting(
    user: AbstractUser, obj: Union[Meeting, ReactionButton]
) -> bool:
    meeting = None
    if isinstance(obj, ReactionButton):
        meeting = obj.meeting
    elif isinstance(obj, Meeting):
        meeting = obj
    return user.has_perm(MeetingPermissions.VIEW, meeting)


@predicate
def is_button_active(user: AbstractUser, obj: ReactionButton) -> bool:
    return isinstance(obj, ReactionButton) and obj.active


@predicate
def has_list_users_reactions_role(user: AbstractUser, obj: ReactionButton) -> bool:
    return isinstance(obj, ReactionButton) and obj.meeting.has_any_roles(
        user, *obj.list_roles
    )


@predicate
def has_change_own_reaction_role(user: AbstractUser, obj: ReactionButton) -> bool:
    return isinstance(obj, ReactionButton) and obj.meeting.has_any_roles(
        user, *obj.change_roles
    )


@predicate
def is_meeting_moderator(user: AbstractUser, obj: ReactionButton):
    return isinstance(obj, ReactionButton) and user.has_perm(
        MeetingPermissions.MODERATE, obj.meeting
    )


rules.add_perm(ReactionButtonPermissions.ADD, is_not_archived & is_moderator)
rules.add_perm(ReactionButtonPermissions.CHANGE, user_can_change_meeting)
rules.add_perm(ReactionButtonPermissions.DELETE, user_can_change_meeting)
rules.add_perm(ReactionButtonPermissions.VIEW, user_can_view_meeting)
rules.add_perm(
    ReactionButtonPermissions.LIST_REACTIONS,
    is_meeting_moderator | has_list_users_reactions_role,
)
rules.add_perm(
    ReactionButtonPermissions.CHANGE_REACTION,
    is_button_active & has_change_own_reaction_role,
)
