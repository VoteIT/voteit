from __future__ import annotations


from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY
from django.contrib.auth.signals import user_logged_in
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
from voteit.organisation import LOGIN_PROVIDER_SESSION_KEY
from voteit.organisation.channels import OrganisationChannel
from voteit.organisation.jobs import email_login_method_added
from voteit.organisation.messages import OrganisationChanged
from voteit.organisation.models import Organisation
from voteit.organisation.models import OrganisationRoles
from voteit.organisation.utils import get_enabled_backends
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


@receiver(user_logged_in)
def remember_login_provider(request=None, user=None, **kw):
    """
    Note which login method this session signed in with.

    An organisation can offer several, and afterwards nothing on the user says
    which one was used -- so the frontend has no way to end the session at the
    provider as well. This reads the auth backend ``django.contrib.auth`` has
    just recorded, which covers every route in.

    It has to run here rather than in the pipeline: ``login()`` flushes the
    session when the person signing in is not the one who was signed in before,
    which would throw away anything written earlier. By the time this signal
    fires, the session keys are set and nothing else will clear them.

    A login that came from no social backend -- the switch-user action,
    ``force_login`` in tests -- leaves whatever was there alone.
    """
    session = getattr(request, "session", None)
    if session is None:
        return
    path = session.get(BACKEND_SESSION_KEY)
    for name, backend in get_enabled_backends().items():
        if f"{backend.__module__}.{backend.__qualname__}" == path:
            session[LOGIN_PROVIDER_SESSION_KEY] = name
            return


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
