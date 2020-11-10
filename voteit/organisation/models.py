from django.conf import settings
from django.db import models

from voteit.core.models import BaseContent


class Organisation(BaseContent):
    managers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="manager_in_orgs"
    )
    meeting_creators = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="meeting_creator_in_orgs"
    )
