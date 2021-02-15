from __future__ import annotations
from typing import TYPE_CHECKING, Union

import rules
from django.contrib.auth.models import AbstractUser
from voteit.core.decorators import predicate
from voteit.core.rules import is_not_archived
from voteit.meeting.models import Meeting
from voteit.meeting.permissions import MeetingPermissions
from voteit.meeting.rules import is_moderator
from voteit.reactions.models import ReactionButton, Reaction
from voteit.reactions.permissions import ReactionButtonPermissions, ReactionPermissions

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
def is_button_active(user: AbstractUser, obj: Union[Reaction, ReactionButton]) -> bool:
    if isinstance(obj, ReactionButton):
        button = obj
    elif isinstance(obj, Reaction):
        button = obj.button
    else:
        return False
    return button.active


@predicate
def has_list_users_reactions_role(user: AbstractUser, obj: ReactionButton) -> bool:
    return isinstance(obj, ReactionButton) and obj.meeting.has_any_roles(
        user, *obj.list_roles
    )


@predicate
def has_change_own_reaction_role(
    user: AbstractUser, obj: Union[Reaction, ReactionButton]
) -> bool:
    # This require all reaction permissions to be exactly the same regardless of any agenda items state
    # Do we want to check permissions against the context we add the reaction on instead?
    if isinstance(obj, Reaction):
        meeting = obj.button.meeting
        roles = obj.button.change_roles
    elif isinstance(obj, ReactionButton):
        meeting = obj.meeting
        roles = obj.change_roles
    else:
        return False
    return meeting.has_any_roles(user, *roles)


@predicate
def is_meeting_moderator(user: AbstractUser, obj: ReactionButton):
    return isinstance(obj, ReactionButton) and user.has_perm(
        MeetingPermissions.MODERATE, obj.meeting
    )


@predicate
def is_reaction_owner(user: AbstractUser, obj: Reaction):
    return isinstance(obj, Reaction) and user == obj.user


# Button
rules.add_perm(ReactionButtonPermissions.ADD, is_not_archived & is_moderator)
rules.add_perm(ReactionButtonPermissions.CHANGE, user_can_change_meeting)
rules.add_perm(ReactionButtonPermissions.DELETE, user_can_change_meeting)
rules.add_perm(ReactionButtonPermissions.VIEW, user_can_view_meeting)
rules.add_perm(
    ReactionButtonPermissions.LIST_REACTIONS,
    is_meeting_moderator | has_list_users_reactions_role,
)
rules.add_perm(
    ReactionPermissions.ADD,
    is_button_active & has_change_own_reaction_role,
)

# Reaction
rules.add_perm(
    ReactionPermissions.DELETE,
    is_reaction_owner & is_button_active & has_change_own_reaction_role,
)

# And the specific for deleting a reaction
