from django.db.models.signals import post_save
from django.dispatch import receiver
from typing import Type

from voteit.access_policy.models import MeetingAccessPolicies
from voteit.meeting.models import Meeting


@receiver(post_save, sender=Meeting)
def create_meeting_access_policies(sender: Type[Meeting], instance: Meeting, created: bool, **kwargs):
    """ Meetings should always have a 1-1 relation with meeting access policies.
    """
    if created:
        MeetingAccessPolicies.objects.create(meeting=instance)
