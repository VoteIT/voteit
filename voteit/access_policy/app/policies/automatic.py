from logging import getLogger
from typing import List

from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.translation import gettext_lazy as _

from voteit.access_policy.models import AccessPolicy
from voteit.access_policy.registries import access_policies

__all__ = ["AutomaticAccess"]
logger = getLogger(__name__)


@access_policies
class AutomaticAccess(AccessPolicy):
    """
    >>> from voteit.meeting.models import Meeting
    >>> meeting = Meeting.objects.create()
    >>> aa = AutomaticAccess.objects.create(meeting=meeting)
    """

    name: str = "automatic"
    title: str = _("Give users access automatically")
    roles_given: List[str] = ArrayField(models.CharField(max_length=20), default=tuple)

    def assign(self, user: AbstractUser):
        if self.roles_given:
            self.meeting.add_roles(user, *self.roles_given)

    def save(self, **kw):
        for role_name in self.roles_given:
            if role_name not in self.meeting.roles_cls.valid_roles:
                raise ValueError(f"{role_name} is not a valid role for meeting")
        super().save(**kw)
