from django.contrib.auth import get_user_model
from social_core.exceptions import AuthException
from django.utils.translation import gettext as _

from voteit.organisation.roles import ROLE_ORG_MANAGER

User = get_user_model()


def org_active(strategy, details, backend, user=None, *args, **kwargs):
    if not backend.organisation.active:
        raise AuthException(backend, _("This organisation is no longer active."))


def social_user(backend, uid, user=None, *args, **kwargs):
    """
    Custom version that authenticates a different user in case one is already logged in.
    """
    provider = backend.name
    social = backend.strategy.storage.user.get_social_auth(provider, uid)
    if social:
        if user and social.user != user:
            # FIXME: We want to reauthenticate as that user instead.
            raise AuthException(
                backend, _("You're logged in as another user, logout first.")
            )
        if not user:
            user = social.user
        if user.identity_id != uid:
            user.identity_id = uid
            user.save()
    elif existing_user_qs := backend.organisation.users.filter(identity_id=uid):
        if (
            existing_user := existing_user_qs.exclude(last_login__isnull=True)
            .order_by("-last_login")
            .first()
        ):
            user = existing_user
        elif existing_user := existing_user_qs.first():
            # Match users without login?
            user = existing_user
        if user and existing_user != user:
            # FIXME: We want to reauthenticate as that user instead.
            raise AuthException(
                backend, _("You're logged in as another user, logout first.")
            )
        user = existing_user

    return {
        "social": social,
        "user": user,
        "is_new": user is None,
        "new_association": social is None,
    }


def create_user(strategy, details, backend, uid, user=None, *args, **kwargs):
    if user:
        return {"is_new": False}
    fields = {
        name: kwargs.get(name, details.get(name))
        for name in backend.setting("USER_FIELDS", ["username", "email"])
    }
    if not fields:
        return
    organisation = backend.organisation
    return {
        "is_new": True,
        "user": strategy.create_user(
            organisation=organisation, identity_id=uid, **fields
        ),
    }


def inherit_users(details, backend, user, response, *args, **kwargs):
    if extra_identity_ids := response.get("extra_identity_ids"):
        backend.organisation.users.filter(
            identity_id__in=extra_identity_ids, is_active=True
        ).update(identity_id=user.identity_id)


def bump_permissions(backend, user, social, *args, **kwargs):
    # No not Djangos!
    if social.extra_data.get("is_superuser", False):
        backend.organisation.add_roles(user, ROLE_ORG_MANAGER)
