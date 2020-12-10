from __future__ import annotations

from django.dispatch import Signal, receiver
from typing import TYPE_CHECKING, List

from voteit.core.messages import RolesAdded, RolesRemoved
from voteit.messaging.channels.user import UserChannel

if TYPE_CHECKING:
    from voteit.core.models import Roles
    from voteit.core.role import Role


roles_added = Signal(providing_args=["sender", "instance", "roles"])
roles_removed = Signal(providing_args=["sender", "instance", "roles"])


@receiver(roles_added)
def push_roles_added(instance: Roles, roles: List[Role], **kwargs):
    user_channel = UserChannel.from_instance(instance.user)
    msg = RolesAdded.create(
        roles=instance.context.roles_to_strings(*roles),
        pk=instance.context.pk,
        model=instance.context.__class__.__name__,
    )
    user_channel.publish(msg)


@receiver(roles_removed)
def push_roles_removed(instance: Roles, roles: List[Role], **kwargs):
    user_channel = UserChannel.from_instance(instance.user)
    msg = RolesRemoved.create(
        roles=instance.context.roles_to_strings(*roles),
        pk=instance.context.pk,
        model=instance.context.__class__.__name__,
    )
    user_channel.publish(msg)
