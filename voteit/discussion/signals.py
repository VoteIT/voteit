from __future__ import annotations

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.discussion.messages import (
    DiscussionPostAdded,
    DiscussionPostChanged,
    DiscussionPostDeleted,
)
from voteit.discussion.models import DiscussionPost
from voteit.discussion.rest_api.serializers import DiscussionPostDetailSerializer
from voteit.messaging.messages.app_state import AppState
from voteit.messaging.signals import channel_subscribed


@receiver(channel_subscribed, sender=AgendaItemChannel)
def _channel_subscribed(context: AgendaItem, app_state: AppState, **kw):
    """ Populate app_state with current discussions """
    app_state.append_from_queryset(
        context.get_discussions(), DiscussionPostDetailSerializer, DiscussionPostAdded
    )


@receiver(post_save, sender=DiscussionPost)
def discussion_post_change(instance=None, created=None, **kw):
    if instance.agenda_item is None:
        return
    ch = AgendaItemChannel.from_instance(instance.agenda_item)
    data = DiscussionPostDetailSerializer(instance).data
    if created:
        msg = DiscussionPostAdded({}, **data)
    else:
        msg = DiscussionPostChanged({}, **data)
    ch.publish(msg)


@receiver(pre_delete, sender=DiscussionPost)
def discussion_post_delete(instance=None, **kw):
    if instance.agenda_item is None:
        return
    ch = AgendaItemChannel.from_instance(instance.agenda_item)
    msg = DiscussionPostDeleted({}, pk=instance.pk)
    ch.publish(msg)
