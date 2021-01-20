from django.dispatch import receiver

from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.messaging.messages.app_state import AppState
from voteit.messaging.signals import channel_subscribed
from voteit.poll.rest_api.serializers import PollDetailSerializer

from .channels import PollChannel
from .messages import PollAdded
from .messages import PollStatus
from .models import Poll


@receiver(channel_subscribed, sender=PollChannel)
def poll_subscribed(context: Poll, app_state: AppState, **kw):
    """ Populate app_state with current poll status """
    msg = PollStatus.create(
        pk=context.pk,
        voted=context.method.vote_set.count(),
        total=context.electoral_register.voters.count(),
    )
    app_state.append(msg)


@receiver(channel_subscribed, sender=MeetingChannel)
def meeting_subscribed(context: Meeting, app_state: AppState, **kw):
    """ Populate app_state with current meeting polls """
    app_state.append_from_queryset(
        context.polls.all(),
        PollDetailSerializer,
        PollAdded
    )
