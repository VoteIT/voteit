from __future__ import annotations


from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from voteit.agenda.channels import AgendaItemChannel
from voteit.core.decorators import disable_on_raw_save
from voteit.discussion.messages import DiscussionPostChanged
from voteit.discussion.messages import DiscussionPostDeleted
from voteit.discussion.models import DiscussionPost
from voteit.discussion.rest_api.serializers import DiscussionPostDetailSerializer


@receiver(post_save, sender=DiscussionPost)
@disable_on_raw_save
def discussion_post_change(instance=None, **kw):
    if instance.agenda_item is None:  # pragma: no cover
        return
    ch = AgendaItemChannel.from_instance(instance.agenda_item)
    data = DiscussionPostDetailSerializer(instance).data
    ch.sync_publish(DiscussionPostChanged(payload=data))


@receiver(pre_delete, sender=DiscussionPost)
def discussion_post_delete(instance=None, **kw):
    if instance.agenda_item is None:  # pragma: no cover
        return
    ch = AgendaItemChannel.from_instance(instance.agenda_item)
    msg = DiscussionPostDeleted(payload={"pk": instance.pk})
    ch.sync_publish(msg)
