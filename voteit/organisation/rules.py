from __future__ import annotations

from typing import TYPE_CHECKING

import rules
from voteit.core.decorators import predicate
from voteit.core.rules import is_user
from voteit.organisation.models import OrganisationContext
from voteit.organisation.permissions import OrgPermissions
from voteit.organisation.permissions import TOSPermissions
from voteit.organisation.permissions import UserConsentPermissions
from voteit.organisation.roles import ROLE_MEETING_CREATOR
from voteit.organisation.roles import ROLE_ORG_MANAGER

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model

    User = get_user_model()


@predicate(role=ROLE_ORG_MANAGER)
def is_manager(user: User, org_context: OrganisationContext):
    """ User has org manager role"""
    return (
        isinstance(org_context, OrganisationContext)
        and org_context.organisation is not None
        and org_context.organisation.has_roles(user, ROLE_ORG_MANAGER)
    )


@predicate(role=ROLE_MEETING_CREATOR)
def is_meeting_creator(user: User, org_context: OrganisationContext):
    """ User has meeting creator role"""
    return (
        isinstance(org_context, OrganisationContext)
        and org_context.organisation is not None
        and org_context.organisation.has_roles(user, ROLE_MEETING_CREATOR)
    )


@predicate
def is_org_user(user: User, org_context):
    """ The user is attached to the organisation"""
    # FIXME: There might be ways to block users from the organisation later on.
    # Django has several ways and we could remove the link to the organisation too.
    return (
        isinstance(org_context, OrganisationContext)
        and getattr(user, "organisation", None) is not None
        and user.organisation == org_context.organisation
    )


# FIXME: This is a stub
rules.add_perm(OrgPermissions.CHANGE, is_manager)
rules.add_perm(OrgPermissions.DELETE, is_manager)
rules.add_perm(OrgPermissions.VIEW, rules.always_allow)
rules.add_perm(OrgPermissions.MANAGE, is_manager)
rules.add_perm(OrgPermissions.CHANGE_ROLES, is_manager)
rules.add_perm(OrgPermissions.VIEW_ROLES, is_manager)  # We might want to change this?


rules.add_perm(TOSPermissions.ADD, is_manager)
rules.add_perm(TOSPermissions.CHANGE, is_manager)
rules.add_perm(TOSPermissions.DELETE, is_manager)
rules.add_perm(TOSPermissions.VIEW, is_org_user)


rules.add_perm(UserConsentPermissions.ADD, is_org_user)
rules.add_perm(UserConsentPermissions.CHANGE, is_user)
# rules.add_perm(UserConsentPermissions.DELETE, is_manager)  # Not really something we deal with?
rules.add_perm(UserConsentPermissions.VIEW, is_user & is_manager)
