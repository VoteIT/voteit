from __future__ import annotations

import rules
from django.contrib.auth.models import AbstractUser

from voteit.core import PERM
from voteit.core.decorators import predicate
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.rules import is_moderator
from voteit.meeting.rules import meeting_upcoming_ongoing
from voteit.reactions import PERM_LIST_REACTIONS
from voteit.reactions.models import Reaction
from voteit.reactions.models import ReactionButton


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
        raise TypeError("obj is not an instance of Reaction or ReactionButton")
    return button.flag_mode


@predicate
def has_list_users_reactions_role_or_moderator(
    user: AbstractUser, obj: ReactionButton
) -> bool:
    if not isinstance(obj, ReactionButton):  # pragma: no coverage
        raise TypeError("obj is not an instance of ReactionButton")
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


_reaction_change_predicate = is_button_active & meeting_upcoming_ongoing & (
    (~is_button_flag & has_change_own_reaction_role_or_moderator)
    | (is_button_flag & is_moderator)
)

# Button
rules.add_perm(
    ReactionButton.get_perm(PERM.ADD), meeting_upcoming_ongoing & is_moderator
)
rules.add_perm(
    ReactionButton.get_perm(PERM.CHANGE), meeting_upcoming_ongoing & is_moderator
)
rules.add_perm(
    ReactionButton.get_perm(PERM.DELETE), meeting_upcoming_ongoing & is_moderator
)
rules.add_perm(
    ReactionButton.get_perm(PERM_LIST_REACTIONS),
    has_list_users_reactions_role_or_moderator,
)
rules.add_perm(ReactionButton.get_perm("set"), _reaction_change_predicate)
rules.add_perm(ReactionButton.get_perm("remove"), _reaction_change_predicate)

# Reaction
rules.add_perm(
    Reaction.get_perm(PERM.ADD),
    is_button_active
    & meeting_upcoming_ongoing
    & (
        (~is_button_flag & has_change_own_reaction_role_or_moderator)
        | (is_button_flag & is_moderator)
    ),
)
rules.add_perm(
    Reaction.get_perm(PERM.DELETE),
    is_button_active
    & meeting_upcoming_ongoing
    & (
        (
            ~is_button_flag
            & is_reaction_owner
            & has_change_own_reaction_role_or_moderator
        )
        | (is_button_flag & is_moderator)
    ),
)
