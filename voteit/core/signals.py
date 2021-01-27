from __future__ import annotations

from django.contrib.auth import get_user_model
from django.dispatch import Signal, receiver
from typing import TYPE_CHECKING, List

from voteit.core.abcs import MeetingContext
from voteit.core.messages import RolesAdded, RolesRemoved

if TYPE_CHECKING:
    from voteit.core.models import Roles
    from voteit.core.role import Role


User = get_user_model()
roles_added = Signal(providing_args=["sender", "instance", "roles"])
roles_removed = Signal(providing_args=["sender", "instance", "roles"])


def _publish(instance, msg):
    from voteit.meeting.channels import MeetingChannel
    from voteit.messaging.channels.user import UserChannel

    if isinstance(instance, MeetingContext):
        meeting = instance.meeting
        if meeting is not None:
            m_channel = MeetingChannel.from_instance(meeting)
            m_channel.publish(msg)
    # FIXME: Duplicate message to user, but we might not send to meeting later on
    # This is a temporary thing
    user_channel = UserChannel.from_instance(instance.user)
    user_channel.publish(msg)


@receiver(roles_added)
def push_roles_added(instance: Roles, roles: List[Role], **kwargs):
    msg = RolesAdded(
        dict(),
        roles=instance.context.roles_to_strings(*roles),
        pk=instance.context.pk,
        model=instance.context.__class__.__name__,
        user_pk=instance.user.pk,
    )
    _publish(instance, msg)


@receiver(roles_removed)
def push_roles_removed(instance: Roles, roles: List[Role], **kwargs):
    msg = RolesRemoved(
        dict(),
        roles=instance.context.roles_to_strings(*roles),
        pk=instance.context.pk,
        model=instance.context.__class__.__name__,
        user_pk=instance.user.pk,
    )
    _publish(instance, msg)
