from __future__ import annotations

from typing import Generator, Type, List, TYPE_CHECKING

from django.db import models
from voteit.access_policy.registries import access_policies
from voteit.meeting.models import Meeting

if TYPE_CHECKING:
    from voteit.access_policy.abcs import AccessPolicy


class MeetingAccessPolicies(models.Model):
    """ Any new access policies should have a relation to this object rather than meeting.
    """

    meeting = models.OneToOneField(
        Meeting, on_delete=models.CASCADE, related_name="access_policies"
    )

    def get_active_policies(self) -> Generator[AccessPolicy]:
        # FIXME: return created policies, are there any saner way?
        for ap in self.get_policies():
            qs = ap.objects.filter(meeting_aps=self, active=True)
            if qs:
                yield qs.first()  # All of them are 1-1 relations

    def get_policies(self) -> List[Type[AccessPolicy]]:
        return access_policies.values()
