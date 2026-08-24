from __future__ import annotations
from contextlib import suppress

from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from voteit.active.components import ActiveUsersComponent
from voteit.active.messages import ActiveUserChanged
from voteit.active.messages import ActiveUsers
from voteit.active.models import ActiveUser
from voteit.components.models import MeetingComponent
from voteit.core.decorators import disable_on_raw_save
from voteit.core.decorators import on_transaction_commit
from voteit.meeting.channels import broadcast_meeting
from voteit.meeting.models import MeetingRoles


@receiver(post_save, sender=MeetingComponent)
def send_active_state_when_enabled(instance: MeetingComponent, **kwargs):
    if instance.component_name == ActiveUsersComponent.name and instance.enabled:
        users = list(instance.meeting.active_users.values_list("user_id", flat=True))
        msg = ActiveUsers(payload={"users": users, "meeting": instance.meeting.pk})
        broadcast_meeting(instance.meeting, msg)


def _send_active_user(*, instance: ActiveUser, active: bool):
    with suppress(ObjectDoesNotExist):
        msg = ActiveUserChanged(
            payload={
                "user": instance.user_id,
                "active": active,
                "meeting": instance.meeting.pk,
            }
        )
        broadcast_meeting(instance.meeting, msg)


@disable_on_raw_save
@receiver(post_save, sender=ActiveUser)
def _send_active_user_created(*, instance: ActiveUser, created, **kwargs):
    if created:
        _send_active_user(instance=instance, active=True)


@on_transaction_commit
@receiver(pre_delete, sender=ActiveUser)
def _send_active_user_deleted(*, instance: ActiveUser, **kwargs):
    _send_active_user(instance=instance, active=False)


@receiver(pre_delete, sender=MeetingRoles)
def remove_active_user(instance: MeetingRoles, **kwargs):
    instance.context.active_users.filter(user=instance.user).delete()
