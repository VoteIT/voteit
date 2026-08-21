from __future__ import annotations


from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from voteit.meeting.channels import MeetingChannel
from voteit.participant_tags.messages import ParticipantTagsChanged
from voteit.participant_tags.models import ParticipantTags


@receiver(post_save, sender=ParticipantTags)
def send_tags_updated(instance: ParticipantTags, created=False, **kwargs):
    if created:
        # We don't need to sent on create, tags will be updated after create
        return
    ch = MeetingChannel(instance.meeting_id)
    msg = ParticipantTagsChanged(
        payload={
            "user": instance.user_id,
            "meeting": instance.meeting_id,
            "tags": instance.tags,
        }
    )
    ch.sync_publish(msg)


@receiver(pre_delete, sender=ParticipantTags)
def send_tags_removed(instance: ParticipantTags, **kwargs):
    ch = MeetingChannel(instance.meeting_id)
    msg = ParticipantTagsChanged(
        payload={"user": instance.user_id, "meeting": instance.meeting_id, "tags": {}}
    )
    ch.sync_publish(msg)
