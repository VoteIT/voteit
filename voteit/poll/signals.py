from django.dispatch import receiver

from voteit.messaging.messages.app_state import AppState
from voteit.messaging.signals import channel_subscribed

from .channels import PollChannel
from .messages import PollStatus
from .models import Poll


@receiver(channel_subscribed, sender=PollChannel)
def channel_subscribed(context: Poll, app_state: AppState, **kw):
    """ Populate app_state with current poll status """
    msg = PollStatus.create(
        pk=context.pk,
        voted=context.method.vote_set.count(),
        total=context.electoral_register.voters.count(),
    )
    app_state.append(msg)
