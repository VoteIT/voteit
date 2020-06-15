from __future__ import annotations
from typing import TYPE_CHECKING
import rules
from django.contrib.auth.models import User

from voteit.organisation.permissions import OrgPermissions

if TYPE_CHECKING:
    from voteit.organisation.models import Organisation


@rules.predicate
def is_manager(user: User, organisation: Organisation):
    return organisation.managers.filter(pk=user.pk).exists()


@rules.predicate
def is_meeting_creator(user: User, organisation: Organisation):
    return organisation.meeting_creators.filter(pk=user.pk).exists()


# Object permissions
# FIXME: This is a stub
rules.add_perm(OrgPermissions.ADD, is_manager)
rules.add_perm(OrgPermissions.CHANGE, is_manager)
rules.add_perm(OrgPermissions.DELETE, is_manager)
rules.add_perm(OrgPermissions.VIEW, is_manager)
rules.add_perm(OrgPermissions.MANAGE, is_manager)
