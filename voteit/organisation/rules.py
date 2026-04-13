from __future__ import annotations

from typing import TYPE_CHECKING

import rules

from voteit.core import PERM
from voteit.core.decorators import predicate
from voteit.organisation.models import Organisation
from voteit.organisation.roles import ROLE_MEETING_CREATOR
from voteit.organisation.roles import ROLE_ORG_MANAGER

if TYPE_CHECKING:
    from voteit.core.models import User


@predicate(role=ROLE_ORG_MANAGER)
def is_manager(user: User, *args):
    """User has org manager role"""
    if user.organisation_id:
        return user.organisation.has_roles(user, ROLE_ORG_MANAGER)
    return False


@predicate(role=ROLE_MEETING_CREATOR)
def is_meeting_creator(user: User, *args):
    """User has any role able to create a meeting"""
    if user.organisation_id:
        return user.organisation.has_any_roles(
            user, ROLE_MEETING_CREATOR, ROLE_ORG_MANAGER
        )
    return False


rules.add_perm(Organisation.get_perm(PERM.CHANGE), is_manager)
rules.add_perm(Organisation.get_perm(PERM.MANAGE), is_manager)
rules.add_perm(Organisation.get_perm(PERM.CHANGE_ROLES), is_manager)
rules.add_perm(Organisation.get_perm(PERM.VIEW_ROLES), is_manager)
