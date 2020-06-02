from abc import abstractmethod

from django.db import models
from django.utils.functional import cached_property
from typing import List, Union, Type

from voteit.core.role import get_valid_roles
from voteit.core.role import Role
from voteit.core.role import roles
from voteit.meeting.models import Meeting


class AccessPolicy(models.Model):
    """ Subclass this to create an access policy.

        The tests for this class are in voteit.access_policy.app.automatic
    """

    active = models.BooleanField()
    meeting_aps = models.OneToOneField(
        "access_policy.MeetingAccessPolicies",
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

    @cached_property
    def meeting(self) -> Meeting:
        return self.meeting_aps.meeting

    def get_valid_roles(self) -> List[Type[Role]]:
        return get_valid_roles(self.meeting)

    def prep_roles(self, *role_list: List[Union[str, Type[Role]]]) -> List[Role]:
        """ Take a list of role classes or strings. Check that
            they're valid for a meeting context and return the role instance for
            this specific meeting.
        """
        results = []
        for role in role_list:
            if isinstance(role, str):
                role = roles[role]
            if role.valid_for(self.meeting):
                results.append(role(self.meeting))
            else:  # pragma: no cover
                raise ValueError(f"Role {role} is not assignable to meetings.")
        return results
