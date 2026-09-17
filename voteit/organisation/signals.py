from __future__ import annotations


from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.test.signals import setting_changed
from social_core.backends.utils import load_backends
from social_django.models import UserSocialAuth
from voteit.messaging.channels import UserChannel

from voteit.core.decorators import disable_on_raw_save
from voteit.core.decorators import on_transaction_commit
from voteit.core.messages.role_updates import RolesChanged
from voteit.core.messages.role_updates import RolesRemoved
from voteit.core.role import Role
from voteit.core.signals import roles_added
from voteit.core.signals import roles_removed
from voteit.core.utils import get_model_shortname
from voteit.organisation.channels import OrganisationChannel
from voteit.organisation.jobs import email_login_method_added
from voteit.organisation.messages import OrganisationChanged
from voteit.organisation.models import Organisation
from voteit.organisation.models import OrganisationRoles
from voteit.organisation.rest_api.serializers import OrganisationSerializer


@receiver(setting_changed)
def reload_social_backends(setting, **kw):
    """
    Keep social_core's backend cache in step with AUTHENTICATION_BACKENDS.

    load_backends() caches globally and ignores its argument once warm, so
    override_settings(AUTHENTICATION_BACKENDS=...) would otherwise be a silent
    no-op. Only fires under test overrides.
    """
    if setting == "AUTHENTICATION_BACKENDS":
        load_backends(settings.AUTHENTICATION_BACKENDS, force_load=True)


@receiver(post_save, sender=UserSocialAuth)
@disable_on_raw_save
@on_transaction_commit
def notify_login_method_added(instance: UserSocialAuth, created=False, **kw):
    """
    Someone gaining a second way into their account should hear about it.

    A first credential is a registration, not an addition, so it stays quiet.
    Anything beyond that was either asked for -- in which case the mail is a
    receipt -- or was not, in which case it is the only way the account's owner
    finds out, and the disconnect endpoint is how they undo it.
    """
    if not created:
        return
    user = instance.user
    if not user.email or user.social_auth.count() < 2:
        return
    email_login_method_added.delay(social_auth_pk=instance.pk)


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
