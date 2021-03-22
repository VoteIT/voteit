from __future__ import annotations

from typing import List
from typing import TYPE_CHECKING

from django.db.models.signals import class_prepared
from django.dispatch import Signal
from django.dispatch import receiver

from voteit.core.abcs import MeetingContext
from voteit.core.messages import RolesAdded
from voteit.core.messages import RolesRemoved
from voteit.core.utils import get_model_shortname
from voteit.core import models_to_register

if TYPE_CHECKING:
    from voteit.core.models import Roles
    from voteit.core.role import Role
    from django.db.models import Model


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
        mm=dict(),
        roles=instance.context.roles_to_strings(*roles),
        pk=instance.context.pk,
        model=get_model_shortname(instance.context),
        user_pk=instance.user.pk,
    )
    _publish(instance, msg)


@receiver(roles_removed)
def push_roles_removed(instance: Roles, roles: List[Role], **kwargs):
    msg = RolesRemoved(
        mm=dict(),
        roles=instance.context.roles_to_strings(*roles),
        pk=instance.context.pk,
        model=get_model_shortname(instance.context),
        user_pk=instance.user.pk,
    )
    _publish(instance, msg)


@receiver(class_prepared)
def deferred_register_model(sender: Model, **kw):
    """Prep register models in content registry.
    Done in apps ready()
    """

    models_to_register.add(sender)
