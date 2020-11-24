from abc import abstractmethod

from django.db import models
from typing import List, Union

from voteit.core.models import ABCModel
from voteit.core.role import Role
from voteit.meeting.roles import MeetingRoles


class AccessPolicy(ABCModel):
    """ Subclass this to create an access policy.

        The tests for this class are in voteit.access_policy.app.automatic
    """

    active = models.BooleanField(default=False)
    meeting = models.OneToOneField(
        "meeting.Meeting",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s",
    )

    class Meta:
        abstract = True

    @property
    @abstractmethod
    def name(self) -> str:
        """ Name of access policy, used as ID.
        """

    @property
    @abstractmethod
    def title(self) -> str:
        """ Human readable name
        """

    def prep_roles(self, *role_list: List[Union[str, Role]]) -> List[Role]:
        """ Take a list of role classes or strings. Check that
            they're valid for a meeting context and return the role instance for
            this specific meeting.
        """
        results = []
        for role in role_list:
            if isinstance(role, str):
                role = MeetingRoles.valid_roles[role]
            elif isinstance(role, Role):
                assert role.name in MeetingRoles.valid_roles
            else:  # pragma: no cover
                raise ValueError(f"{role} is not assignable to meetings or not a role.")
            results.append(role)
        return results
