from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from voteit.core.signals import after_sm_transition
from voteit.messaging.signals import channel_subscribed

from voteit.components.messages import MeetingComponentChanged
from voteit.components.messages import MeetingComponentDeleted
from voteit.components.rest_api.serializers import MeetingComponentSerializer
from voteit.components.utils import get_meeting_component_adapters
from voteit.core.decorators import disable_on_raw_save
from voteit.core.decorators import on_transaction_commit
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.components.models import MeetingComponent
from voteit.meeting.statemachines import MeetingStateMachine

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.messaging.state import AppState


@receiver(channel_subscribed, sender=MeetingChannel)
def meeting_channel_subscribed(
    context: Meeting, app_state: AppState, user: AbstractUser, **kw
):
    """
    Send active components
    """
    # Append enabled components
    for component in context.components.all():
        if component.is_valid:
            app_state.append(
                MeetingComponentChanged(
                    payload=MeetingComponentSerializer(component).data
                )
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
    is_valid = data["is_valid"]
    if created:
        if is_valid:
            meeting_ch.sync_publish(MeetingComponentChanged(payload=data))
    else:
        # Update
        meeting_ch.sync_publish(
            MeetingComponentChanged(payload=data)
            if is_valid
            else MeetingComponentDeleted(payload=data)
        )


@receiver(pre_delete, sender=MeetingComponent)
def meeting_component_delete(instance=None, **kw):
    meeting_ch = MeetingChannel.from_instance(instance.meeting)
    msg = MeetingComponentDeleted(payload={"pk": instance.pk})
    # Sent after transaction commit!
    meeting_ch.sync_publish(msg)


@receiver(after_sm_transition, sender=Meeting)
def disable_components_when_meeting_closes(
    instance: Meeting, source, target, event, **kw
):
    if target.value == MeetingStateMachine.closed.value:
        disable_names = [
            k
            for (k, v) in get_meeting_component_adapters().items()
            if v.disable_on_close
        ]
        for component in instance.meeting.components.filter(
            component_name__in=disable_names, enabled=True
        ):
            component.disable()
            component.save()
