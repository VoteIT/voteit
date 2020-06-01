from logging import getLogger

from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from django.db import models
from typing import List, Type, Union

from voteit.access_policy.abcs import AccessPolicy
from voteit.access_policy.registries import access_policies
from voteit.core.role import get_valid_roles, roles, Role

__all__ = ["AutomaticAccess"]
logger = getLogger(__name__)

@access_policies
class AutomaticAccess(AccessPolicy):
    name = "automatic"
    title = _("Give users access automatically")
    roles_given: str = models.TextField(_("Roles given"), null=True, blank=True)

    def get_valid_roles(self):
        return sorted(get_valid_roles(self.meeting_aps.meeting), key=lambda x: x.title.lower())

    def set_roles(self, *assign_roles: List[Union[str, Type[Role]]]):
        names = []
        for role in assign_roles:
            if isinstance(role, str):
                role = roles[role]
            if role.valid_for(self.meeting):
                names.append(role.name)
            else:  # pragma: no cover
                raise ValueError(f"Role {role} is not assignable to meetings.")
        self.roles_given = ",".join(names)

    def get_roles(self):
        found_roles = []
        valid_roles = self.get_valid_roles()
        if self.roles_given:
            for role_name in self.roles_given.split(","):
                if role_name in roles:
                    role = roles[role_name]
                    if role in valid_roles:
                        found_roles.append(role)
                    else:  # pragma: no cover
                        logger.warning("AutomaticAccess with pk %s has an invalid role: %s", self.pk, role_name)
        return found_roles

    def assign(self, user: User):
        for role in self.get_roles():
            rinst = role(self.meeting)
            rinst.add(user)
