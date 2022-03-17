from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from envelope.app.user_channel.channel import UserChannel
from envelope.signals import channel_subscribed
from voteit.agenda.channels import AgendaItemChannel
from voteit.core.decorators import disable_on_raw_save
from voteit.core.utils import get_model_shortname
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.signals import archive_meeting
from voteit.reactions.messages import ButtonAdded
from voteit.reactions.messages import ButtonChanged
from voteit.reactions.messages import ButtonDeleted
from voteit.reactions.messages import ReactionCount
from voteit.reactions.messages import UserReactionAdded
from voteit.reactions.messages import UserReactionDeleted
from voteit.reactions.models import Reaction
from voteit.reactions.models import ReactionButton
from voteit.reactions.rest_api.serializers import ButtonDetailSerializer
from voteit.reactions.rest_api.serializers import ReactionSerializer


if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from envelope.utils import AppState
    from voteit.meeting.models import Meeting
    from voteit.agenda.models import AgendaItem


@receiver(channel_subscribed, sender=MeetingChannel)
def meeting_channel_subscribed(
    context: Meeting, app_state: AppState, user: AbstractUser, **kw
):
    app_state.append_from_queryset(
        context.reaction_buttons.all(), ButtonDetailSerializer, ButtonAdded
    )


@receiver(channel_subscribed, sender=AgendaItemChannel)
def ai_channel_subscribed(
    context: AgendaItem, app_state: AppState, user: AbstractUser, **kw
):
    """Send users own reactions and the total count for this agenda items content"""
    all_buttons = (
        context.reactions.values("content_type", "object_id", "button")
        .annotate(count=Count("pk"))
        .order_by()
    )
    for button in all_buttons:
        # FIXME: Serializer should handle this
        ct = ContentType.objects.get_for_id(button["content_type"])
        model = ct.model_class()
        button["content_type"] = get_model_shortname(model)
        app_state.append(ReactionCount(**button))
    # Users own reactions
    app_state.append_from_queryset(
        context.reactions.filter(user=user), ReactionSerializer, UserReactionAdded
    )


@receiver(post_save, sender=ReactionButton)
@disable_on_raw_save
def reaction_button_updated(
    instance: ReactionButton = None, created: bool = None, **kw
):
    ch = MeetingChannel.from_instance(instance.meeting)
    data = ButtonDetailSerializer(instance).data
    if created:
        msg = ButtonAdded(data=data)
    else:
        msg = ButtonChanged(data=data)
    ch.sync_publish(msg)


@receiver(pre_delete, sender=ReactionButton)
def reaction_button_delete(instance: ReactionButton = None, **kw):
    ch = MeetingChannel.from_instance(instance.meeting)
    msg = ButtonDeleted(pk=instance.pk)
    ch.sync_publish(msg)


def _send_count(instance: Reaction, pre_delete=False):
    # TODO: Discuss: This could be done much more efficient if we send many button reactions.
    # For a full ai, or for a set of buttons, do it all in one query.
    # The signal for subscribing to AI should use that method.
    try:
        ai = instance.agenda_item
    except AttributeError:  # pragma: no cover
        return
    if ai is None:
        return
    count = instance.object.reaction_set.filter(button=instance.button).count()
    if pre_delete:
        count -= 1
    msg = ReactionCount(
        content_type=get_model_shortname(instance.content_type.model_class()),
        object_id=instance.object_id,
        button=instance.button.pk,
        count=count,
    )
    ch = AgendaItemChannel.from_instance(ai)
    ch.sync_publish(msg)


@receiver(post_save, sender=Reaction)
@disable_on_raw_save
def send_count_saved(instance: Reaction = None, created: bool = None, **kw):
    if created:
        # Update should never happen
        _send_count(instance)


@receiver(post_save, sender=Reaction)
@disable_on_raw_save
def send_added_to_user(instance: Reaction = None, created: bool = None, **kw):
    """This is a message that goes to the user channel for the specific user who added the reaction.
    It's not a reply to the action that the reaction was added, but a consequence.
    The reason it's not a response is simply that the user may have several browser tabs open,
    and things should appear as marked there too.
    """
    if created:
        # Update shouldn't exist
        data = ReactionSerializer(instance).data
        msg = UserReactionAdded(data=data)
        user_ch = UserChannel.from_instance(instance.user)
        user_ch.sync_publish(msg)


@receiver(pre_delete, sender=Reaction)
def send_count_deleted(instance: Reaction = None, **kw):
    _send_count(instance, pre_delete=True)


@receiver(pre_delete, sender=Reaction)
def send_deleted_to_user(instance: Reaction = None, **kw):
    """Same as send_added_to_user, sent to userchannel instead of a response."""
    msg = UserReactionDeleted(pk=instance.pk)
    user_ch = UserChannel.from_instance(instance.user)
    user_ch.sync_publish(msg)


@receiver(archive_meeting)
def disable_buttons(meeting: Meeting, **kw):
    """Archived meetings shouldn't have active buttons."""
    for button in meeting.reaction_buttons.filter(active=True):
        button.active = False
        button.save()
