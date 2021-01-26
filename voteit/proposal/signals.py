from django.dispatch import receiver

from voteit.agenda.channels import AgendaItemChannel
from voteit.agenda.models import AgendaItem
from voteit.messaging.messages.app_state import AppState
from voteit.messaging.signals import channel_subscribed

from .messages import ProposalAdded
from .rest_api.serializers import ProposalDetailSerializer


@receiver(channel_subscribed, sender=AgendaItemChannel)
def _channel_subscribed(context: AgendaItem, app_state: AppState, **kw):
    """ Populate app_state with current proposals """
    app_state.append_from_queryset(
        context.get_proposals(),
        ProposalDetailSerializer,
        ProposalAdded
    )
