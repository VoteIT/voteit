from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.dispatch import receiver

from envelope.app.user_channel.channel import UserChannel
from envelope.signals import channel_subscribed

from voteit.core.decorators import disable_on_raw_save
from voteit.core.messages.role_updates import RolesAdded, RolesRemoved
from voteit.core.utils import get_model_shortname

from .channels import OrganisationChannel
from .messages import OrganisationChanged
from .models import Organisation, OrganisationRoles
from .rest_api.serializers import OrganisationSerializer
from ..core.role import Role
from ..core.signals import roles_added, roles_removed

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from envelope.utils import AppState


@receiver(post_save, sender=Organisation)
@disable_on_raw_save
def organisation_change(instance, created=None, **kw):
    if not created:
        data = OrganisationSerializer(instance).data
        ch = OrganisationChannel.from_instance(instance)
        msg = OrganisationChanged(data=data)
        ch.sync_publish(msg)


@receiver(channel_subscribed, sender=OrganisationChannel)
def meeting_channel_subscribed(
    context: Organisation, app_state: AppState, user: AbstractUser, **kw
):
    """
    Send users meeting roles as response
    """
    roles = context.get_roles(user)
    if roles:
        msg = RolesAdded(
            mm=dict(),
            roles=context.roles_to_strings(*roles),
            pk=context.pk,
            model=get_model_shortname(context),
            user_pk=user.pk,
        )
        app_state.append(msg)


def _role_msg_publish(instance: OrganisationRoles, msg):
    organisation_ch = OrganisationChannel.from_instance(instance.context)
    organisation_ch.sync_publish(msg)
    # FIXME: Duplicate message to user, but we might not send to meeting later on
    # This is a temporary thing
    user_ch = UserChannel.from_instance(instance.user)
    user_ch.sync_publish(msg)


@receiver(roles_added, sender=OrganisationRoles)
@disable_on_raw_save
def push_roles_added(instance: OrganisationRoles, roles: list[Role], **kwargs):
    _role_msg_publish(
        instance,
        RolesAdded(
            mm=dict(),
            roles=instance.context.roles_to_strings(*roles),
            pk=instance.context.pk,
            model=get_model_shortname(instance.context),
            user_pk=instance.user.pk,
        ),
    )


@receiver(roles_removed, sender=OrganisationRoles)
def push_roles_removed(instance: OrganisationRoles, roles: list[Role], **kwargs):
    _role_msg_publish(
        instance,
        RolesRemoved(
            mm=dict(),
            roles=instance.context.roles_to_strings(*roles),
            pk=instance.context.pk,
            model=get_model_shortname(instance.context),
            user_pk=instance.user.pk,
        ),
    )
