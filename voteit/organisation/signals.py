from __future__ import annotations


from django.db.models.signals import post_save
from django.dispatch import receiver
from voteit.messaging.channels import UserChannel

from voteit.core.decorators import disable_on_raw_save
from voteit.core.messages.role_updates import RolesChanged
from voteit.core.messages.role_updates import RolesRemoved
from voteit.core.role import Role
from voteit.core.signals import roles_added
from voteit.core.signals import roles_removed
from voteit.core.utils import get_model_shortname
from voteit.organisation.channels import OrganisationChannel
from voteit.organisation.messages import OrganisationChanged
from voteit.organisation.models import Organisation
from voteit.organisation.models import OrganisationRoles
from voteit.organisation.rest_api.serializers import OrganisationSerializer


@receiver(post_save, sender=Organisation)
@disable_on_raw_save
def organisation_change(instance, created=None, **kw):
    if not created:
        data = OrganisationSerializer(instance).data
        ch = OrganisationChannel.from_instance(instance)
        msg = OrganisationChanged(payload=data)
        ch.sync_publish(msg)


def _role_msg_publish(instance: OrganisationRoles, msg):
    organisation_ch = OrganisationChannel.from_instance(instance.context)
    organisation_ch.sync_publish(msg)
    # This is a temporary thing
    user_ch = UserChannel.from_instance(instance.user)
    user_ch.sync_publish(msg)


@receiver(roles_added, sender=OrganisationRoles)
@disable_on_raw_save
def push_roles_added(instance: OrganisationRoles, roles: list[Role], **kwargs):
    _role_msg_publish(
        instance,
        RolesChanged(
            payload={
                "roles": roles,
                "pk": instance.context.pk,
                "model": get_model_shortname(instance.context),
                "user_pk": instance.user.pk,
            }
        ),
    )


@receiver(roles_removed, sender=OrganisationRoles)
def push_roles_removed(instance: OrganisationRoles, roles: list[Role], **kwargs):
    _role_msg_publish(
        instance,
        RolesRemoved(
            payload={
                "roles": roles,
                "pk": instance.context.pk,
                "model": get_model_shortname(instance.context),
                "user_pk": instance.user.pk,
            }
        ),
    )
