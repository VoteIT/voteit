from django.contrib.auth import get_user_model
from django.contrib.auth import login
from social_core.exceptions import AuthException
from django.utils.translation import gettext as _
from social_django.models import UserSocialAuth

from voteit.organisation.roles import ROLE_ORG_MANAGER

User = get_user_model()


def org_active(strategy, details, backend, user=None, *args, **kwargs):
    if not backend.organisation.active:
        raise AuthException(backend, _("This organisation is no longer active."))


def _reauth_user(backend, user):
    redirect_name = "next"
    next_url = backend.strategy.session_get(redirect_name)
    login(
        backend.strategy.request,
        user=user,
        backend=f"{backend.__class__.__module__}.{backend.__class__.__name__}",
    )
    if next_url and not backend.strategy.session_get(redirect_name):
        backend.strategy.session_set(redirect_name, next_url)


def _transfer_social_auths(from_user, to_user, provider):
    """
    Move all social auth records for provider from from_user to to_user.
    No conflict check needed: UserSocialAuth has a global unique constraint on
    (provider, uid), so the same uid can never exist on two users simultaneously.
    """
    UserSocialAuth.objects.filter(user=from_user, provider=provider).update(
        user=to_user
    )


def social_user(backend, uid, user=None, *args, **kwargs):
    """
    Custom version that authenticates a different user in case one is already logged in.

    Handles two loop-causing scenarios with pre-existing/duplicate accounts:
    - social.user is inactive: prefer an active user with the same identity_id
    - identity_id lookup: only consider active users to avoid picking deactivated duplicates
    """
    provider = backend.name
    social = backend.strategy.storage.user.get_social_auth(provider, uid)
    if social:
        if user and social.user != user:
            # Odd case, this is a duplicate user that's authenticated, we may want to move the social auth...
            if user.is_active and user.identity_id == uid:
                social.user = user
                social.save()
            else:
                _reauth_user(backend, social.user)
                return {
                    "social": social,
                    "user": social.user,
                    "is_new": False,
                    "new_association": False,
                }
        if not user:
            user = social.user
        # If the resolved user is inactive (e.g. old merged account still holds the social auth),
        # prefer an active user with the same identity_id in the same org.
        if user and not user.is_active:
            active_user = (
                backend.organisation.users.filter(identity_id=uid, is_active=True)
                .order_by("-last_login")
                .first()
            )
            if active_user:
                social.user = active_user
                social.save()
                _transfer_social_auths(user, active_user, provider)
                user = active_user
    elif existing_user_qs := backend.organisation.users.filter(
        identity_id=uid, is_active=True
    ):
        existing_user = (
            existing_user_qs.exclude(last_login__isnull=True)
            .order_by("-last_login")
            .first()
        )
        if not existing_user:
            # Anyone active, regardless of login history
            existing_user = existing_user_qs.first()
        if existing_user and user != existing_user:
            if user:
                _transfer_social_auths(user, existing_user, provider)
            _reauth_user(backend, existing_user)
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


def ensure_userid(backend, user, *args, **kwargs):
    if user and not user.userid:
        from voteit.core.utils import generate_valid_userid

        userid = generate_valid_userid(user)
        if userid:
            user.userid = userid
            user.save(update_fields=["userid"])


def inherit_users(backend, user, response, uid, *args, **kwargs):
    if not user:
        return
    if user.identity_id != uid:
        user.identity_id = uid
        user.save()
    if extra_identity_ids := response.get("extra_identity_ids"):
        backend.organisation.users.filter(
            identity_id__in=extra_identity_ids, is_active=True
        ).update(identity_id=user.identity_id)


def bump_permissions(backend, user, social, *args, **kwargs):
    # No not Djangos!
    if social.extra_data.get("is_superuser", False):
        backend.organisation.add_roles(user, ROLE_ORG_MANAGER)


def remove_nonmatching_email(backend, user, social, *args, **kwargs):
    try:
        provider_scopes = backend.organisation.provider.scope.split()
    except AttributeError:
        provider_scopes = []
    if "email" not in provider_scopes:
        return
    if emails := social.extra_data.get("user_data", {}).get("email", []):
        if user.email not in emails:
            user.email = emails[0]
            user.save()
    elif user.email:
        user.email = ""
        user.save()
