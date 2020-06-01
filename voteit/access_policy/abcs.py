from abc import abstractmethod

from django.db import models
from django.utils.functional import cached_property


class AccessPolicy(models.Model):
    """ Subclass this to create an access policy.
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
    def meeting(self):
        return self.meeting_aps.meeting
