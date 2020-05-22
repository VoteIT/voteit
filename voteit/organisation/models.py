from django.contrib.auth.models import User
from django.db import models
from voteit.core.models import BaseContent


class Organisation(BaseContent):
    managers = models.ManyToManyField(User, blank=True, related_name="manager_in_orgs")
    meeting_creators = models.ManyToManyField(
        User, blank=True, related_name="meeting_creator_in_orgs"
    )
