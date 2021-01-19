from django.contrib.auth.models import AbstractUser
from django.dispatch import receiver
from voteit.agenda.messages import AgendaAdded

from voteit.agenda.rest_api.serializers import AgendaItemSerializer
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.messaging.messages.app_state import AppState
from voteit.messaging.signals import channel_subscribed


@receiver(channel_subscribed, sender=MeetingChannel)
def meeting_channel_subscribed(context: Meeting, app_state: AppState, user: AbstractUser, **kw):
    """ Send agenda items to client. """
    # TODO Filter based on user permissions (client handle if showing private ai:s for now)
    app_state.append_from_queryset(
        context.agenda_items.all(),
        AgendaItemSerializer,
        AgendaAdded
    )
