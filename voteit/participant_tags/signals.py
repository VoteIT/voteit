from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from voteit.messaging.state import AppState
from voteit.messaging.signals import channel_subscribed

from voteit.meeting.channels import MeetingChannel
from voteit.participant_tags.components import GenderTags
from voteit.participant_tags.components import PronounTags
from voteit.participant_tags.messages import AllParticipantTags
from voteit.participant_tags.messages import ParticipantTagsChanged
from voteit.participant_tags.models import ParticipantTags

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting


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


@receiver(channel_subscribed, sender=MeetingChannel)
def send_all_tags(context: Meeting, app_state: AppState, **kw):
    # FIXME: These are the only two existing adapters. If we create more, fetch this differently.
    if context.meeting.component_enabled(
        GenderTags.name
    ) or context.meeting.component_enabled(PronounTags.name):
        tags = defaultdict(list)
        # Note on order_by, it's mostly for testing
        for row in context.participant_tags.order_by("user_id").values(
            "user_id", "tags"
        ):
            for ns, tag_vals in row["tags"].items():
                if isinstance(tag_vals, str):
                    tag_vals = [tag_vals]
                for v in tag_vals:
                    tags[f"{ns}:{v}"].append(row["user_id"])
        msg = AllParticipantTags(payload={"meeting": context.pk, "tags": tags})
        app_state.append(msg)
