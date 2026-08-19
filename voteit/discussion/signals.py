from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from voteit.messaging.signals import channel_subscribed

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.core.decorators import disable_on_raw_save
from voteit.discussion.messages import DiscussionPostChanged
from voteit.discussion.messages import DiscussionPostDeleted
from voteit.discussion.models import DiscussionPost
from voteit.discussion.rest_api.serializers import DiscussionPostDetailSerializer

if TYPE_CHECKING:
    from voteit.messaging.state import AppState


@receiver(channel_subscribed, sender=AgendaItemChannel)
def _channel_subscribed(context: AgendaItem, app_state: AppState, **kw):
    """
    Populate app_state with current discussions
    """
    serializer = DiscussionPostDetailSerializer(
        context.get_discussions(),
        many=True,
    )
    if serializer.data:
        app_state.add_batch(DiscussionPostChanged, serializer.data)


@receiver(post_save, sender=DiscussionPost)
@disable_on_raw_save
def discussion_post_change(instance=None, created=None, **kw):
    if instance.agenda_item is None:  # pragma: no cover
        return
    ch = AgendaItemChannel.from_instance(instance.agenda_item)
    data = DiscussionPostDetailSerializer(instance).data
    if created:
        msg = DiscussionPostChanged(payload=data)
    else:
        msg = DiscussionPostChanged(payload=data)
    ch.sync_publish(msg)


@receiver(pre_delete, sender=DiscussionPost)
def discussion_post_delete(instance=None, **kw):
    if instance.agenda_item is None:  # pragma: no cover
        return
    ch = AgendaItemChannel.from_instance(instance.agenda_item)
    msg = DiscussionPostDeleted(payload={"pk": instance.pk})
    ch.sync_publish(msg)
