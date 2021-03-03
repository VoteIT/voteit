from __future__ import annotations

from typing import List
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.db.models.signals import class_prepared
from django.dispatch import Signal
from django.dispatch import receiver

from voteit.core.abcs import MeetingContext
from voteit.core.messages import RolesAdded
from voteit.core.messages import RolesRemoved

if TYPE_CHECKING:
    from voteit.core.models import Roles
    from voteit.core.role import Role
    from django.db.models import Model


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


@receiver(class_prepared)
def register_model(sender: Model, **kw):
    """Register models in content registry.

    Models should be here after class_prepared is called
    >>> from voteit.core.registries import content_types
    >>> "meeting" in content_types
    True

    Registering the same model twice should raise errors
    >>> from voteit.meeting.models import Meeting
    >>> register_model(Meeting)
    Traceback (most recent call last):
    ...
    ValueError: ...

    """
    from voteit.core.registries import content_types

    if hasattr(sender, "name"):
        # Only care about models with name
        if sender.name is None:
            sender.name = sender.__name__.lower()
        if sender.name in content_types:
            raise ValueError(
                f"{sender.name} is already present in content registry. \n"
                f"Existing: {content_types[sender.name]}\n"
                f"Tried to register {sender}"
            )
        content_types[sender.name] = sender
