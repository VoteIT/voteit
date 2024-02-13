from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django_fsm import post_transition
from envelope.signals import channel_subscribed

from voteit.components.messages import MeetingComponentAdded
from voteit.components.messages import MeetingComponentChanged
from voteit.components.messages import MeetingComponentDeleted
from voteit.components.rest_api.serializers import MeetingComponentSerializer
from voteit.components.utils import get_meeting_component_adapters
from voteit.core.decorators import disable_on_raw_save
from voteit.core.decorators import on_transaction_commit
from voteit.core.workflows import EnabledWf
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.components.models import MeetingComponent
from voteit.meeting.workflows import MeetingWf

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from envelope.utils import AppState


@receiver(channel_subscribed, sender=MeetingChannel)
def meeting_channel_subscribed(
    context: Meeting, app_state: AppState, user: AbstractUser, **kw
):
    """
    Send active components
    """
    # Append enabled components
    for component in context.components.filter(state=EnabledWf.ON):
        if component.is_valid:
            app_state.append(
                MeetingComponentAdded(**MeetingComponentSerializer(component).data)
            )


@receiver(post_save, sender=MeetingComponent)
@disable_on_raw_save
@on_transaction_commit
def meeting_component_updated(instance: MeetingComponent = None, created=None, **kw):
    """
    Components behave a bit differently from other things. We really only care about enabled components.
    If they're disabled, they should even be deleted from the frontends datalayer.

    To actually edit components (including disabled ones) we'll use the ones from the rest endpoint.
    """
    meeting_ch = MeetingChannel.from_instance(instance.meeting)
    data = MeetingComponentSerializer(instance).data
    component_on = data["state"] == EnabledWf.ON
    is_valid = data["is_valid"]
    msg = None
    if created:
        if component_on and is_valid:
            msg = MeetingComponentAdded(**data)
    else:
        # Update
        if component_on and is_valid:
            # Only send if valid
            msg = MeetingComponentChanged(**data)
        else:
            msg = MeetingComponentDeleted(**data)
    if msg:
        meeting_ch.sync_publish(msg)


@receiver(pre_delete, sender=MeetingComponent)
def meeting_component_delete(instance=None, **kw):
    meeting_ch = MeetingChannel.from_instance(instance.meeting)
    msg = MeetingComponentDeleted(pk=instance.pk)
    # Sent after transaction commit!
    meeting_ch.sync_publish(msg)


@receiver(post_transition, sender=Meeting)
def disable_components_when_meeting_closes(
    instance: Meeting, source: str, target: str, **kw
):
    if target == MeetingWf.CLOSED:
        disable_names = [
            k
            for (k, v) in get_meeting_component_adapters().items()
            if v.disable_on_close
        ]
        for component in instance.meeting.components.filter(
            component_name__in=disable_names, state=EnabledWf.ON
        ):
            component.disable()
            component.save()
