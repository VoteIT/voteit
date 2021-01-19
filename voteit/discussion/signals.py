from django.dispatch import receiver

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.messaging.messages.app_state import AppState
from voteit.messaging.signals import channel_subscribed

from .messages import DiscussionPostAdded
from .rest_api.serializers import DiscussionPostDetailSerializer


@receiver(channel_subscribed, sender=AgendaItemChannel)
def channel_subscribed(context: AgendaItem, app_state: AppState, **kw):
    """ Populate app_state with current discussions """
    for discussion in context.get_discussions():
        app_state.append_from(discussion, DiscussionPostDetailSerializer, DiscussionPostAdded)
