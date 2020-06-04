from logging import getLogger
from typing import List, Type, Union

from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _

from voteit.access_policy.models import AccessPolicy
from voteit.access_policy.registries import access_policies
from voteit.core.role import Role

__all__ = ["AutomaticAccess"]
logger = getLogger(__name__)


@access_policies
class AutomaticAccess(AccessPolicy):
    name = "automatic"
    title = _("Give users access automatically")
    roles_given: str = models.TextField(_("Roles given"), null=True, blank=True)

    def set_given_roles(self, *given_roles: List[Union[str, Type[Role]]]):
        """ Set roles that any user requesting access should be given.
        """
        role_instances = self.prep_roles(*given_roles)
        self.roles_given = ",".join([r.name for r in role_instances])

    def get_role_instances(self) -> List[Role]:
        if self.roles_given:
            return self.prep_roles(*self.roles_given.split(","))
        return []

    def assign(self, user: User):
        for role in self.get_role_instances():
            role.add(user)
