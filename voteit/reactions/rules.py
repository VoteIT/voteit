from __future__ import annotations

import rules
from django.contrib.auth.models import AbstractUser

from voteit.core.decorators import predicate
from voteit.core.rules import is_not_archived
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.rules import can_view_meeting
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import meeting_upcoming_ongoing
from voteit.reactions.models import Reaction
from voteit.reactions.models import ReactionButton
from voteit.reactions.permissions import ReactionButtonPermissions
from voteit.reactions.permissions import ReactionPermissions


@predicate
def is_button_active(user: AbstractUser, obj: Reaction | ReactionButton) -> bool:
    if isinstance(obj, ReactionButton):
        button = obj
    elif isinstance(obj, Reaction):
        button = obj.button
    else:  # pragma: no coverage
        raise TypeError("obj is not a Reaction or ReactionButton")
    return button.active


@predicate
def is_button_flag(user: AbstractUser, obj: Reaction | ReactionButton) -> bool:
    if isinstance(obj, ReactionButton):
        button = obj
    elif isinstance(obj, Reaction):
        button = obj.button
    else:  # pragma: no coverage
        # We don't want to return a bool here since this must be negatable
        raise TypeError(f"obj is not an instance of Reaction or ReactionButton")
    return button.flag_mode


@predicate
def has_list_users_reactions_role_or_moderator(
    user: AbstractUser, obj: ReactionButton
) -> bool:
    if not isinstance(obj, ReactionButton):  # pragma: no coverage
        raise TypeError(f"obj is not an instance of ReactionButton")
    roles = obj.list_roles
    if ROLE_MODERATOR not in roles:
        roles.append(ROLE_MODERATOR)
    return obj.meeting.has_any_roles(user, *roles)


@predicate
def has_change_own_reaction_role_or_moderator(
    user: AbstractUser, obj: Reaction | ReactionButton
) -> bool:
    # This requires all reaction permissions to be exactly the same regardless of any agenda items state
    # Do we want to check permissions against the context we add the reaction on instead?
    if isinstance(obj, Reaction):
        meeting = obj.button.meeting
        roles = obj.button.change_roles
    elif isinstance(obj, ReactionButton):
        meeting = obj.meeting
        roles = obj.change_roles
    else:  # pragma: no coverage
        raise TypeError("obj is not an instance of Reaction or ReactionButton")
    # Moderator should always have that permission
    if ROLE_MODERATOR not in roles:
        roles.append(ROLE_MODERATOR)
    return meeting.has_any_roles(user, *roles)


@predicate
def is_reaction_owner(user: AbstractUser, obj: Reaction):
    return isinstance(obj, Reaction) and user == obj.user


# Button
rules.add_perm(
    ReactionButtonPermissions.ADD,
    is_not_archived & is_moderator,
)
rules.add_perm(
    ReactionButtonPermissions.CHANGE, meeting_upcoming_ongoing & is_moderator
)
rules.add_perm(
    ReactionButtonPermissions.DELETE, meeting_upcoming_ongoing & is_moderator
)
rules.add_perm(ReactionButtonPermissions.VIEW, can_view_meeting)
rules.add_perm(
    ReactionButtonPermissions.LIST_REACTIONS,
    has_list_users_reactions_role_or_moderator,
)

# Reaction
rules.add_perm(
    ReactionPermissions.ADD,
    is_button_active
    & (
        (~is_button_flag & has_change_own_reaction_role_or_moderator)
        | (is_button_flag & is_moderator)
    ),
)
rules.add_perm(
    ReactionPermissions.DELETE,
    is_button_active
    & (
        (
            ~is_button_flag
            & is_reaction_owner
            & has_change_own_reaction_role_or_moderator
        )
        | (is_button_flag & is_moderator)
    ),
)
