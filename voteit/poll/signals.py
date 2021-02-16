from __future__ import annotations

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from voteit.meeting.channels import MeetingChannel
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


@receiver(channel_subscribed, sender=PollChannel)
def poll_subscribed(context: Poll, app_state: AppState, **kw):
    """ Populate app_state with current poll status """
    msg = PollStatus.create(
        pk=context.pk,
        voted=context.votes.count(),
        total=context.electoral_register.voters.count(),
    )
    app_state.append(msg)


@receiver(channel_subscribed, sender=MeetingChannel)
def meeting_subscribed(context: Meeting, app_state: AppState, **kw):
    """ Populate app_state with current meeting polls """
    app_state.append_from_queryset(context.polls.all(), PollDetailSerializer, PollAdded)


@receiver(post_save, sender=Poll)
def poll_change(instance=None, created=None, **kw):
    if instance.meeting is not None:
        ch = MeetingChannel.from_instance(instance.meeting)
        data = PollDetailSerializer(instance).data
        if created:
            msg = PollAdded({}, **data)
        else:
            msg = PollChanged({}, **data)
        ch.publish(msg)


@receiver(pre_delete, sender=Poll)
def poll_delete(instance=None, **kw):
    if instance.meeting is not None:
        ch = MeetingChannel.from_instance(instance.meeting)
        msg = PollDeleted({}, pk=instance.pk)
        ch.publish(msg)
