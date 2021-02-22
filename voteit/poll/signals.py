from __future__ import annotations

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from voteit.agenda.workflows import AgendaItemWf
from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.models import Meeting
from voteit.messaging.messages.app_state import AppState
from voteit.messaging.signals import channel_subscribed
from voteit.poll.channels import PollChannel
from voteit.poll.messages import PollAdded
from voteit.poll.messages import PollChanged
from voteit.poll.messages import PollDeleted
from voteit.poll.messages import PollStatus
from voteit.poll.models import Poll
from voteit.poll.rest_api.serializers import PollDetailSerializer
from voteit.poll.workflows import PollWf


@receiver(channel_subscribed, sender=PollChannel)
def poll_subscribed(context: Poll, app_state: AppState, **kw):
    """ Populate app_state with current poll status """
    msg = PollStatus.create(
        pk=context.pk,
        voted=context.votes.count(),
        total=context.electoral_register.voters.count(),
    )
    app_state.append(msg)


@receiver(channel_subscribed, sender=ParticipantsChannel)
def participants_subscribed(context: Meeting, app_state: AppState, **kw):
    """ Populate app_state with current meeting polls, except private ones """
    app_state.append_from_queryset(
        context.polls.exclude(state=PollWf.PRIVATE).exclude(
            agenda_item__state=AgendaItemWf.PRIVATE
        ),
        PollDetailSerializer,
        PollAdded,
    )


@receiver(channel_subscribed, sender=ModeratorsChannel)
def moderators_subscribed(context: Meeting, app_state: AppState, **kw):
    """ Populate app_state with current meeting polls """
    app_state.append_from_queryset(context.polls.all(), PollDetailSerializer, PollAdded)


@receiver(post_save, sender=Poll)
def poll_change(instance: Poll = None, created: bool = None, **kw):
    if instance.meeting is not None:
        instance.refresh_from_db(
            fields=["result_data"]
        )  # FIXME somewhere else, preferably.
        data = PollDetailSerializer(instance).data
        participants_ch = ParticipantsChannel.from_instance(instance.meeting)
        moderators_ch = ModeratorsChannel.from_instance(instance.meeting)
        if created:
            msg = PollAdded({}, **data)
        else:
            msg = PollChanged({}, **data)
        if instance.is_private:
            # Only care about transmitting to participants if it existed previously
            if not created:
                participants_msg = PollDeleted(pk=instance.pk)
                participants_ch.publish(participants_msg)
        elif instance.agenda_item is None or not instance.agenda_item.is_private:
            # Publish if ai isn't private
            participants_ch.publish(msg)
        moderators_ch.publish(msg)


@receiver(pre_delete, sender=Poll)
def poll_delete(instance: Poll = None, **kw):
    """ Poll deleted is only sent to moderators if the poll's private"""
    if instance.meeting is not None:
        moderators_ch = ModeratorsChannel.from_instance(instance.meeting)
        msg = PollDeleted({}, pk=instance.pk)
        moderators_ch.publish(msg)
        # Publish to participants if poll isn't private. If agenda item exists, make sure it's not private
        if not instance.is_private:
            if instance.agenda_item is None or not instance.agenda_item.is_private:
                participants_ch = ParticipantsChannel.from_instance(instance.meeting)
                participants_ch.publish(msg)
