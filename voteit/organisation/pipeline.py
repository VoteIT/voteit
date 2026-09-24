from logging import getLogger
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.conf import settings
from django.contrib.auth import login
from social_core.exceptions import AuthException
from social_core.pipeline.partial import partial
from django.utils.translation import gettext as _
from social_django.models import UserSocialAuth

from voteit.core.loggers import log_auth
from voteit.organisation import IDPROXY_PROVIDER
from voteit.organisation.matching import find_candidates
from voteit.organisation.matching import is_elevated
from voteit.organisation.matching import names_match
from voteit.organisation.models import TermsOfService
from voteit.organisation.roles import ROLE_ORG_MANAGER
from voteit.organisation.utils import get_enabled_backends
from voteit.organisation.utils import accept_tos
from voteit.organisation.utils import get_active_tos
from voteit.organisation.utils import get_tos_to_accept

logger = getLogger(__name__)
User = get_user_model()

#: Set by ``POST /api/user/connect/``, consumed by :func:`require_connect_intent`.
#: Holds the provider_id the user meant to attach.
CONNECT_INTENT_SESSION_KEY = "voteit_connect_intent"


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


def _transfer_social_auths(from_user, to_user, provider: str | None = None):
    """
    Move social auth records from from_user to to_user, one provider or all.
    No conflict check needed: UserSocialAuth has a global unique constraint on
    (provider, uid), so the same uid can never exist on two users simultaneously.
    """
    qs = UserSocialAuth.objects.filter(user=from_user)
    if provider is not None:
        qs = qs.filter(provider=provider)
    qs.update(user=to_user)


def social_user(backend, uid, user=None, *args, **kwargs):
    """
    Custom version that authenticates a different user in case one is already logged in.

    Handles two loop-causing scenarios with pre-existing/duplicate accounts:
    - social.user is inactive: prefer an active user with the same identity_id
    - identity_id lookup: only consider active users to avoid picking deactivated duplicates

    All of that is the id proxy's, and only the id proxy's: ``identity_id``
    holds an id proxy identifier, so no other provider's uid may ever be looked
    up in it. Every other backend resolves by credential alone, which is what
    stock PSA does -- matching one of those to an existing account is the
    account matcher's job, not this step's.
    """
    provider = backend.name
    social = backend.strategy.storage.user.get_social_auth(provider, uid)
    if provider != IDPROXY_PROVIDER:
        if social:
            if user and social.user != user:
                # Someone else's session is open in this browser. The credential
                # says who just proved themselves, so log that person in rather
                # than leaving the other one signed in.
                _reauth_user(backend, social.user)
            user = social.user
        return {
            "social": social,
            "user": user,
            "is_new": user is None,
            "new_association": social is None,
        }
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


def require_connect_intent(backend, uid, user=None, *args, **kwargs):
    """
    A signed-in account only picks up a new login method on purpose.

    Runs before ``social_user``, so ``user`` here is whoever the browser is
    signed in as and nothing has resolved the credential yet. If that person is
    about to have an unknown credential attached to their account without having
    asked for it -- B walking up to A's open session on a shared computer and
    logging in with ScoutID -- drop the session user and let the rest of the
    pipeline treat this as the fresh login it really is. ``django.contrib.auth``
    flushes the session when a different user logs in, so nothing of A's
    survives.

    The intent is popped whatever happens, so a flag can never sit in the
    session waiting to wave through some later login.
    """
    intent = backend.strategy.session_pop(CONNECT_INTENT_SESSION_KEY)
    if user is None:
        return
    if backend.strategy.storage.user.get_social_auth(backend.name, uid):
        # A credential we already know. Whose it is, is social_user's call.
        return
    if intent == backend.name:
        return
    logger.info(
        "Unintended %s association refused for user %s; continuing as a new login",
        backend.name,
        user.pk,
    )
    return {"user": None}


#: Field the resume request carries the decision in.
LINK_ACCOUNT_FIELD = "link_account"
#: Value meaning "none of these, give me a new account".
LINK_ACCOUNT_NEW = "new"
#: Field the resume request carries the accepted terms of service pk in.
ACCEPT_TOS_FIELD = "accept_tos"


def _elevated_message(backend, candidate) -> str:
    """
    Why this login was refused, and what to do instead.

    Names the login methods the account actually has, because "sign in the way
    you usually do" is no help to somebody who has just been told no.
    """
    backends = get_enabled_backends()
    titles = sorted(
        backends[name].get_title()
        for name in candidate.social_auth.values_list("provider", flat=True)
        if name in backends
    )
    if not titles:
        # Elevated, matched, and no way to sign in to it. Nothing they can do
        # from here, so do not pretend otherwise.
        return _(
            "You already have an account here that manages the organisation, "
            "but it has no way to sign in. Ask another organisation manager "
            "for help."
        )
    return _(
        "You already have an account here that manages the organisation. Sign "
        "in with %(existing)s instead, then connect %(new)s from your profile."
    ) % {"existing": " or ".join(titles), "new": backend.get_title()}


def _link_account_url(strategy, token: str) -> str:
    base = getattr(settings, "LINK_ACCOUNT_URL", "/link-account")
    return f"{base}?partial_token={token}"


@partial
def match_existing_user(
    *args,
    strategy,
    backend,
    details,
    current_partial,
    response=None,
    user=None,
    social=None,
    **kwargs,
):
    """
    Work out whether this login belongs to an account that already exists.

    Only reached when nothing else resolved the person: no credential for this
    provider, and no identity the id proxy recognises. A second provider brings
    no shared identifier, so the evidence is the verified address the provider
    vouches for -- see ``voteit.organisation.matching``.

    One account on that address, carrying the same name, that somebody has
    actually used, is taken silently: returned as ``user`` so ``create_user``
    short-circuits and ``associate_user`` attaches the credential to it.

    Anything else **pauses the pipeline** and asks. Nothing is created while the
    question is open, which is the point: an account made first and merged away
    later gets harder to merge the longer it goes unanswered, and a question
    nobody answers turns into support work. Here there is nothing to clean up --
    an abandoned decision is an abandoned login, and the person simply tries
    again.
    """
    if user is not None or social is not None:
        return
    email = backend.get_verified_email(details, response or {})
    candidates = find_candidates(
        backend.organisation, provider=backend.name, email=email
    )
    if not candidates:
        return
    exact = [
        candidate
        for candidate in candidates
        if names_match(candidate, details.get("first_name"), details.get("last_name"))
    ]
    if elevated := [c for c in exact if is_elevated(c)]:
        # This login answers to a manager's account. Letting it through would
        # make a second account that someone has to merge in later; refusing it
        # keeps them on the one path that proves both logins are theirs.
        raise AuthException(backend, _elevated_message(backend, elevated[0]))
    # An elevated account on the same address under another name is somebody
    # else's, and never on offer.
    choices = [candidate for candidate in candidates if not is_elevated(candidate)]
    if len(exact) == 1 and exact[0].last_login and exact[0] in choices:
        logger.info(
            "Matched %s login to existing user %s on a verified email and name",
            backend.name,
            exact[0].pk,
        )
        return {"user": exact[0], "matched_existing": True}
    if not choices:
        return
    answer = strategy.request_data().get(LINK_ACCOUNT_FIELD)
    if answer == LINK_ACCOUNT_NEW:
        return
    if answer:
        # Never trust the pk on its own: it only counts if it is still one of
        # the accounts this login could have claimed.
        picked = {str(candidate.pk): candidate for candidate in choices}.get(answer)
        if picked is not None:
            return {"user": picked, "matched_existing": True}
    return strategy.redirect(_link_account_url(strategy, current_partial.token))


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
    if backend.name == IDPROXY_PROVIDER:
        # identity_id is an id proxy identifier. An account created by any other
        # provider simply has none, and is reached through its UserSocialAuth.
        fields["identity_id"] = uid
    return {
        "is_new": True,
        "user": strategy.create_user(organisation=organisation, **fields),
    }


def ensure_userid(backend, user, *args, **kwargs):
    if user and not user.userid:
        from voteit.core.utils import generate_valid_userid

        userid = generate_valid_userid(user)
        if userid:
            user.userid = userid
            user.save(update_fields=["userid"])


def inherit_users(backend, user, response, uid, *args, **kwargs):
    """
    Keep identity_id in step with the id proxy, which owns it.

    identity_id is an id proxy identifier and nothing else; it is what groups a
    person's id proxy accounts, which ``UserView.alternate`` / ``switch``,
    ``UserMerger`` and the admin duplicate filter all read. Another provider's
    uid must never be written there -- it would claim an identity in a
    namespace it has no part in.
    """
    if not user or backend.name != IDPROXY_PROVIDER:
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
    """
    Sync the user's email against the identity server's email scope data.
    """
    if backend.name != IDPROXY_PROVIDER:
        return
    try:
        provider_scopes = backend.provider.scope.split()
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


def log_new_association(
    backend, user, social, is_new=False, new_association=False, *args, **kwargs
):
    """
    Record a login method being attached to an account that already existed.

    A brand new account picking up its first credential is a registration, not
    a connection, and is not what this is for.
    """
    if not (new_association and user and not is_new):
        return
    matched = kwargs.get("matched_existing")
    extra = {"matched_on": "verified email and name"} if matched else {}
    log_auth(
        "Login method matched to existing account"
        if matched
        else "Login method connected",
        request=backend.strategy.request,
        for_user=user,
        context=backend.organisation,
        provider=backend.name,
        uid=social.uid if social else None,
        **extra,
    )


@partial
def require_tos_accept(*args, strategy, backend, current_partial, user=None, **kwargs):
    """
    Pause the login until the active terms of service are accepted.

    Before ``create_user``, so nobody gets an account without accepting. The
    client resumes with ``accept_tos=<pk>``, and the accept is stored by
    ``store_tos_accept`` once there is a user.
    """
    if user is not None:
        tos = get_tos_to_accept(user)
    else:
        tos = get_active_tos(backend.organisation)
    if tos is None:
        return
    # Only the version they were shown counts, a newer one means asking again
    if strategy.request_data().get(ACCEPT_TOS_FIELD) == str(tos.pk):
        return {"accepted_tos": tos.pk}
    base = getattr(settings, "ACCEPT_TOS_URL", "/accept-tos")
    query = urlencode(
        {
            "partial_token": current_partial.token,
            "resume_url": f"/complete/{backend.name}/",
        }
    )
    return strategy.redirect(f"{base}?{query}")


def store_tos_accept(user=None, accepted_tos=None, *args, **kwargs):
    """
    Store what ``require_tos_accept`` got, now that there's a user.
    """
    if user is not None and accepted_tos is not None:
        accept_tos(user, TermsOfService.objects.get(pk=accepted_tos))
