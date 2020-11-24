from __future__ import annotations
from typing import TYPE_CHECKING
import rules
from django.contrib.auth.models import AbstractUser

from voteit.organisation.permissions import OrgPermissions
from voteit.organisation.roles import ROLE_ORG_MANAGER, ROLE_MEETING_CREATOR
from voteit.organisation.models import Organisation
if TYPE_CHECKING:
    pass

@rules.predicate
def is_manager(user: AbstractUser, organisation: Organisation):
    return (isinstance(organisation, Organisation) and organisation.has_roles(user, ROLE_ORG_MANAGER))


@rules.predicate
def is_meeting_creator(user: AbstractUser, organisation: Organisation):
    return (isinstance(organisation, Organisation) and organisation.has_roles(user, ROLE_MEETING_CREATOR))


# Object permissions
# FIXME: This is a stub
rules.add_perm(OrgPermissions.ADD, is_manager)
rules.add_perm(OrgPermissions.CHANGE, is_manager)
rules.add_perm(OrgPermissions.DELETE, is_manager)
rules.add_perm(OrgPermissions.VIEW, is_manager)
rules.add_perm(OrgPermissions.MANAGE, is_manager)
