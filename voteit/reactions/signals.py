from __future__ import annotations
from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from voteit.agenda.channels import AgendaItemChannel
from voteit.meeting.channels import MeetingChannel
from voteit.messaging.channels.user import UserChannel
from voteit.messaging.signals import channel_subscribed
from voteit.reactions.messages import (
    ButtonAdded,
    ButtonChanged,
    ButtonDeleted,
    ReactionCount,
    UserReactionAdded,
    UserReactionDeleted,
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
    """Send users own reactions and the total count for this agenda items content"""
    app_state.append_from_queryset(
        context.reactions.filter(user=user), ReactionSerializer, UserReactionAdded
    )
    # FIXME: This should be optimized in a proper query - this is just a placeholder
    buttons = tuple(context.meeting.reactionbutton_set.filter(active=True))
    if buttons:
        items = set(context.proposals.all()) | set(context.discussions.all())
        for button in buttons:
            for item in items:
                ct = ContentType.objects.get_for_model(item)
                count = Reaction.objects.filter(
                    button=button,
                    object_id=item.pk,
                    content_type=ct,
                ).count()
                # FIXME: Change to natural_key: app.model
                if count:
                    msg = ReactionCount(
                        {},
                        content_type=ct.pk,
                        object_id=item.pk,
                        button=button.pk,
                        count=count,
                    )
                    app_state.append(msg)


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
    count = Reaction.objects.filter(
        button=instance.button,
        object_id=instance.object_id,
        content_type=instance.content_type,
    ).count()
    if pre_delete:
        count -= 1
    msg = ReactionCount(
        {},
        # FIXME: Change to natural_key: app.model
        content_type=instance.content_type.pk,
        object_id=instance.object_id,
        button=instance.button.pk,
        count=count,
    )
    ch = AgendaItemChannel.from_instance(ai)
    ch.publish(msg)


@receiver(post_save, sender=Reaction)
def send_count_saved(instance: Reaction = None, created: bool = None, **kw):
    if created:
        # Update should never happen
        _send_count(instance)


@receiver(post_save, sender=Reaction)
def send_added_to_user(instance: Reaction = None, created: bool = None, **kw):
    """This is a message that goes to the user channel for the specific user who added the reaction.
    It's not a reply to the action that the reaction was added, but a consequence.
    The reason it's not a response is simply that the user may have several browser tabs open,
    and things should appear as marked there too.
    """
    if created:
        # Update shouldn't exist
        data = ReactionSerializer(instance).data
        msg = UserReactionAdded({}, **data)
        user_ch = UserChannel.from_instance(instance.user)
        user_ch.publish(msg)


@receiver(pre_delete, sender=Reaction)
def send_count_deleted(instance: Reaction = None, **kw):
    _send_count(instance, pre_delete=True)


@receiver(pre_delete, sender=Reaction)
def send_deleted_to_user(instance: Reaction = None, **kw):
    """Same as send_added_to_user, sent to userchannel instead of a response."""
    msg = UserReactionDeleted({}, pk=instance.pk)
    user_ch = UserChannel.from_instance(instance.user)
    user_ch.publish(msg)
