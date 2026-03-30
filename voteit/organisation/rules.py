from __future__ import annotations

from typing import TYPE_CHECKING

import rules
from voteit.core.decorators import predicate
from voteit.organisation.permissions import OrgPermissions
from voteit.organisation.roles import ROLE_MEETING_CREATOR
from voteit.organisation.roles import ROLE_ORG_MANAGER

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model

    User = get_user_model()


@predicate(role=ROLE_ORG_MANAGER)
def is_manager(user: User, *args):
    """User has org manager role"""
    if user.organisation_id:
        return user.organisation.has_roles(user, ROLE_ORG_MANAGER)
    return False


@predicate(role=ROLE_MEETING_CREATOR)
def is_meeting_creator(user: User, *args):
    """User has meeting creator role"""
    if user.organisation_id:
        return user.organisation.has_roles(user, ROLE_MEETING_CREATOR)
    return False


# FIXME: This is a stub
rules.add_perm(OrgPermissions.CHANGE, is_manager)
rules.add_perm(OrgPermissions.DELETE, is_manager)
rules.add_perm(OrgPermissions.VIEW, rules.always_allow)
rules.add_perm(OrgPermissions.MANAGE, is_manager)
rules.add_perm(OrgPermissions.CHANGE_ROLES, is_manager)
rules.add_perm(OrgPermissions.VIEW_ROLES, is_manager)  # We might want to change this?
