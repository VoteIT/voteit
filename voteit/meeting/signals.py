from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.messages import MeetingChanged
from voteit.meeting.models import Meeting
from voteit.meeting.rest_api.serializers import MeetingDetailSerializer


@receiver(post_save, sender=Meeting)
def meeting_change(instance, created=None, **kw):
    if not created:
        data = MeetingDetailSerializer(instance).data
        ch = MeetingChannel.from_instance(instance)
        msg = MeetingChanged({}, **data)
        ch.publish(msg)


# FIXME: What about deleted? Some kind of crash and burn message?
