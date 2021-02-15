from __future__ import annotations
from typing import TYPE_CHECKING

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from voteit.agenda.channels import AgendaItemChannel
from voteit.meeting.channels import MeetingChannel
from voteit.messaging.signals import channel_subscribed
from voteit.reactions.messages import (
    ButtonAdded,
    ButtonChanged,
    ButtonDeleted,
    ReactionCount,
    UserReactionAdded,
)
from voteit.reactions.models import ReactionButton, Reaction
from voteit.reactions.rest_api.serializers import (
    ButtonDetailSerializer,
    ReactionSerializer,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.meeting.models import Meeting
    from voteit.messaging.messages.app_state import AppState
    from voteit.agenda.models import AgendaItem


@receiver(channel_subscribed, sender=MeetingChannel)
def meeting_channel_subscribed(
    context: Meeting, app_state: AppState, user: AbstractUser, **kw
):
    app_state.append_from_queryset(
        context.reactionbutton_set.all(), ButtonDetailSerializer, ButtonAdded
    )


@receiver(channel_subscribed, sender=AgendaItemChannel)
def ai_channel_subscribed(
    context: AgendaItem, app_state: AppState, user: AbstractUser, **kw
):
    """ Send users own reactions
    """
    # TODO: We need to send initial reaction count too, right?
    # Reaction count should be done using queryset annotations, and not by multiple queries.
    app_state.append_from_queryset(
        context.reactions.filter(user=user), ReactionSerializer, UserReactionAdded
    )


@receiver(post_save, sender=ReactionButton)
def reaction_button_updated(
    instance: ReactionButton = None, created: bool = None, **kw
):
    ch = MeetingChannel.from_instance(instance.meeting)
    data = ButtonDetailSerializer(instance).data
    if created:
        msg = ButtonAdded({}, **data)
    else:
        msg = ButtonChanged({}, **data)
    ch.publish(msg)


@receiver(pre_delete, sender=ReactionButton)
def reaction_button_delete(instance: ReactionButton = None, **kw):
    ch = MeetingChannel.from_instance(instance.meeting)
    msg = ButtonDeleted({}, pk=instance.pk)
    ch.publish(msg)


def _send_count(instance, pre_delete=False):
    # TODO: Discuss: This could be done much more efficient if we send many button reactions.
    # For a full ai, or for a set of buttons, do it all in one query.
    # The signal for subscribing to AI should use that method.
    try:
        ai = instance.object.agenda_item
    except AttributeError:
        return
    if ai is None:
        return
    # count = ReactionButton.objects.counts_for_object(instance.object)
    count = Reaction.objects.filter(
        button=instance.button,
        # TODO: Discuss: Is there a difference from using object=instance?
        object_id=instance.object_id,
        content_type=instance.content_type,
    ).count()
    if pre_delete:
        count -= 1
    msg = ReactionCount(
        {},
        content_type=instance.content_type.pk,  # TODO: This is not predictable. We probably need model name (.__class__.__name__?)
        object_id=instance.object_id,
        button=instance.button.pk,
        count=count,
    )
    ch = AgendaItemChannel.from_instance(ai)
    ch.publish(msg)


@receiver(post_save, sender=Reaction)
def send_count_saved(instance: Reaction = None, **kw):
    _send_count(instance)


@receiver(pre_delete, sender=Reaction)
def send_count_deleted(instance: Reaction = None, **kw):
    _send_count(instance, pre_delete=True)

# TODO: Incoming signals?
