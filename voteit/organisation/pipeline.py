from logging import getLogger
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth import logout
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware
from social_core.exceptions import AuthPolicyError
from social_core.pipeline.partial import partial
from django.db import models
from django.utils.translation import gettext as _
from social_django.models import UserSocialAuth

from voteit.core.loggers import log_auth
from voteit.core.removal import abort_removal_path
from voteit.core.user_merger import merge_conflicts
from voteit.core.user_merger import pick_merge_target
from voteit.core.user_merger import user_activity_score
from voteit.core.user_merger import log_reassignment
from voteit.core.user_merger import UserMerger
from voteit.meeting.models import Meeting
from voteit.organisation import IDPROXY_PROVIDER
from voteit.organisation.matching import find_candidates
from voteit.organisation.matching import is_elevated
from voteit.organisation.matching import names_match
from voteit.organisation.roles import ROLE_ORG_MANAGER
from voteit.organisation.utils import get_enabled_backends
from voteit.organisation.utils import accept_tos
from voteit.organisation.utils import get_current_tos

logger = getLogger(__name__)
User = get_user_model()

#: Set by ``POST /api/user/connect/``, consumed by :func:`require_connect_intent`.
#: Holds the provider_id the user meant to attach.
CONNECT_INTENT_SESSION_KEY = "voteit_connect_intent"


class LoginRefused(AuthPolicyError):
    """
    A refusal whose message is meant for the person logging in.

    social_core's own exceptions show a generic reason and keep what they were
    given in ``detail``. ``SocialAuthExceptionMiddleware`` renders ``str()``.
    """

    def __str__(self):
        return self.detail or super().__str__()


def org_active(strategy, details, backend, user=None, *args, **kwargs):
    if not backend.organisation.active:
        raise LoginRefused(backend, _("This organisation is no longer active."))


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
    moved = list(qs)
    qs.update(user=to_user)
    for social in moved:
        log_reassignment(social, "user", from_user, to_user)


def find_identity_accounts(organisation, uid: str) -> list:
    """
    Active accounts in this organisation that an id proxy login with ``uid``
    reaches: the ones holding the identity, and the one holding the credential.
    """
    if not uid:
        # identity_id=None would match every account without one.
        return []
    return list(
        organisation.users.filter(
            models.Q(identity_id=uid)
            | models.Q(social_auth__provider=IDPROXY_PROVIDER, social_auth__uid=uid),
            is_active=True,
        )
        .distinct()
        .order_by("pk")
    )


def social_user(backend, uid, user=None, *args, id_key="", **kwargs):
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

    Unlike upstream (6.1) this doesn't resolve ``legacy_identifiers``. Old rows
    got their id_key from ``SOCIAL_AUTH_OLD_ID_KEYS``; changing a backend's
    ID_KEY again needs that lookup added here.
    """
    provider = backend.name
    social = backend.strategy.storage.user.get_social_auth(provider, uid, id_key=id_key)
    if provider == IDPROXY_PROVIDER:
        accounts = find_identity_accounts(backend.organisation, uid)
        if len(accounts) > 1:
            # Nobody is picked or logged in here, resolve_identity_accounts decides.
            return {
                "social": social,
                "user": user,
                "identity_accounts": [account.pk for account in accounts],
                "is_new": False,
                "new_association": social is None,
            }
    else:
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


def require_connect_intent(backend, uid, user=None, *args, id_key="", **kwargs):
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

    With the intent recorded, a credential that already reaches another account
    is refused. ``social_user`` would otherwise switch the session to that
    account -- right for a login, but here the person asked to add a login
    method and would silently land somewhere else.

    The intent is popped whatever happens, so a flag can never sit in the
    session waiting to wave through some later login.
    """
    intent = backend.strategy.session_pop(CONNECT_INTENT_SESSION_KEY)
    if user is None:
        return
    social = backend.strategy.storage.user.get_social_auth(
        backend.name, uid, id_key=id_key
    )
    if intent == backend.name:
        if _reaches_other_account(backend, uid, user, social):
            logger.info(
                "Refused connecting %s to user %s: it belongs to another account",
                backend.name,
                user.pk,
            )
            raise LoginRefused(backend, _connected_elsewhere_message(backend))
        return
    if social:
        # A credential we already know. Whose it is, is social_user's call.
        return
    logger.info(
        "Unintended %s association refused for user %s; continuing as a new login",
        backend.name,
        user.pk,
    )
    return {"user": None}


def _reaches_other_account(backend, uid, user, social) -> bool:
    """
    Whether ``social_user`` would resolve this login to an account other than
    ``user``. Mirrors its id proxy rules: an active account holding the identity
    wins over an inactive credential owner, and an identity the session user
    already holds moves the credential to them.
    """
    owner = social.user if social else None
    if backend.name == IDPROXY_PROVIDER:
        if user.identity_id == uid:
            return False
        if owner is None or not owner.is_active:
            owner = (
                backend.organisation.users.filter(identity_id=uid, is_active=True)
                .exclude(pk=user.pk)
                .first()
                or owner
            )
    return owner is not None and owner != user


def _connected_elsewhere_message(backend) -> str:
    return _(
        "This %(provider)s login already belongs to another account here. Sign "
        "in with %(provider)s to use that account. To connect it to this account "
        "instead, first remove %(provider)s from the other account."
    ) % {"provider": backend.get_title()}


#: Field the resume request carries the decision in.
LINK_ACCOUNT_FIELD = "link_account"
#: Value meaning "none of these, give me a new account".
LINK_ACCOUNT_NEW = "new"
#: Field the resume request carries the accepted terms of service pk in.
ACCEPT_TOS_FIELD = "accept_tos"
#: Field the resume request carries the account picked among duplicates in.
CHOOSE_ACCOUNT_FIELD = "choose_account"
#: Field asking to merge the duplicates instead of picking one.
MERGE_ACCOUNTS_FIELD = "merge_accounts"


def _holds_identity(account, uid: str) -> bool:
    """
    Only these are known to be the person logging in. An account that only
    holds the credential may have got it by mistake, and merging it would
    hand its other login methods to this person.
    """
    return bool(uid) and account.identity_id == uid


def why_not_mergeable(accounts: list, uid: str) -> str | None:
    """
    Why these accounts can't be merged by their owner, or None if they can.
    """
    if not all(_holds_identity(account, uid) for account in accounts):
        return _(
            "One of these accounts isn't tied to your identity, so they can't be "
            "merged here. Contact VoteIT to have them merged."
        )
    if any(account.removal_requested is not None for account in accounts):
        return _(
            "One of these accounts is about to be removed, so they can't be merged."
        )
    if any(is_elevated(account) for account in accounts):
        return _(
            "One of these accounts manages the organisation, so they can't be "
            "merged here. Contact VoteIT to have them merged."
        )
    if conflicts := merge_conflicts(accounts):
        titles = ", ".join(
            Meeting.objects.filter(pk__in=conflicts)
            .order_by("title")
            .values_list("title", flat=True)
        )
        return _(
            "More than one of these accounts has voted, is in an electoral "
            "register or in a group in the same meeting: %(meetings)s"
        ) % {"meetings": titles}
    return None


def _merge_into(backend, sources: list, target) -> None:
    for source in sources:
        # The id proxy just proved this person holds the identity. Callers pass
        # only accounts holding it, or holding nothing but its credential.
        UserMerger(source, target, same_person=True, actor=target).run()
        log_auth(
            "Duplicate account merged at login",
            request=backend.strategy.request,
            for_user=target,
            context=backend.organisation,
            merged_user=source.pk,
        )


def _only_this_credential(account, uid: str) -> bool:
    """
    No login method on it but this id proxy credential, so a merge hands
    nothing of anyone else's to the person logging in.
    """
    return not account.social_auth.exclude(provider=IDPROXY_PROVIDER, uid=uid).exists()


def _merge_unused(backend, uid: str, session_user, accounts: list) -> None:
    """
    Merge accounts nobody has used into the one the person would pick anyway.
    The target always holds the identity.
    """
    accounts = [a for a in accounts if a.removal_requested is None]
    holders = [a for a in accounts if _holds_identity(a, uid)]
    if not holders:
        return
    target = pick_merge_target(holders, session_user)
    unused = [
        account
        for account in accounts
        if account != target
        and user_activity_score(account) == 0
        and (_holds_identity(account, uid) or _only_this_credential(account, uid))
    ]
    if not unused:
        return
    try:
        _merge_into(backend, unused, target)
    except ValueError as exc:
        # Another login merged these first, the caller recomputes the accounts.
        logger.warning(
            "Silent merge at login skipped. Organisation: %s, target: %s, reason: %s",
            backend.organisation.pk,
            target.pk,
            exc,
        )
    except Exception:
        # A bug, not a refusal. The login falls back to asking the person.
        logger.exception(
            "Silent merge at login failed. Organisation: %s, target: %s, users: %s",
            backend.organisation.pk,
            target.pk,
            [account.pk for account in unused],
        )


def _settle(backend, social, session_user, chosen) -> dict:
    """
    Continue the login as ``chosen``, with the credential on it.
    """
    if social is not None and social.user_id != chosen.pk:
        previous = social.user
        # A merge earlier in this step may have deactivated it.
        previous.refresh_from_db(fields=["is_active"])
        social.user = chosen
        social.save()
        if not previous.is_active:
            _transfer_social_auths(previous, chosen, IDPROXY_PROVIDER)
    if session_user is not None and session_user.pk != chosen.pk:
        _reauth_user(backend, chosen)
    return {
        "user": chosen,
        "social": social,
        "is_new": False,
        "new_association": social is None,
        "identity_accounts": None,
    }


def _choose_account_url(token: str, merge_refused: bool = False) -> str:
    base = getattr(settings, "CHOOSE_ACCOUNT_URL", "/choose-account")
    query = {"partial_token": token}
    if merge_refused:
        query["merge_refused"] = "1"
    return f"{base}?{urlencode(query)}"


@partial
def resolve_identity_accounts(
    *args,
    strategy,
    backend,
    uid,
    current_partial,
    user=None,
    social=None,
    identity_accounts=None,
    **kwargs,
):
    """
    One id proxy identity, several active accounts in this organisation.

    Accounts nobody has used are merged away silently, unless one of the
    accounts is elevated. Only accounts holding the identity, without a pending
    removal, take part. If more than one is left, the login **pauses** and the
    person picks one, or asks to merge them. A merge is refused for the reasons
    in ``why_not_mergeable``: that is logged as an error and the person is
    asked to pick one instead.
    """
    if not identity_accounts:
        return
    # Recomputed, the accounts may have changed while the question was open.
    accounts = find_identity_accounts(backend.organisation, uid)
    # A merge moves every login method onto the target, so nothing is merged
    # into a manager's account without anyone being asked.
    if not any(is_elevated(account) for account in accounts):
        _merge_unused(backend, uid, user, accounts)
        accounts = find_identity_accounts(backend.organisation, uid)
    if not accounts:
        return {"user": social.user if social else None, "identity_accounts": None}
    if len(accounts) == 1:
        return _settle(backend, social, user, accounts[0])
    answer = strategy.request_data()
    if picked := answer.get(CHOOSE_ACCOUNT_FIELD):
        # Only counts if it is still one of the accounts this login reaches.
        chosen = {str(account.pk): account for account in accounts}.get(str(picked))
        if chosen is not None:
            return _settle(backend, social, user, chosen)
    elif answer.get(MERGE_ACCOUNTS_FIELD):
        reason = why_not_mergeable(accounts, uid)
        if reason is None:
            target = pick_merge_target(accounts, user)
            try:
                _merge_into(backend, [a for a in accounts if a != target], target)
            except ValueError as exc:
                # UserMerger._validate refused, e.g. another login merged first.
                reason = str(exc)
            except Exception:
                # A bug, not a refusal: keep the traceback, still answer the person.
                logger.exception(
                    "Merge of duplicate accounts failed at login. Organisation: %s, "
                    "users: %s",
                    backend.organisation.pk,
                    [account.pk for account in accounts],
                )
                return strategy.redirect(
                    _choose_account_url(current_partial.token, merge_refused=True)
                )
            else:
                return _settle(backend, social, user, target)
        logger.error(
            "Merge of duplicate accounts refused at login. Organisation: %s, "
            "users: %s, reason: %s",
            backend.organisation.pk,
            [account.pk for account in accounts],
            reason,
        )
        return strategy.redirect(
            _choose_account_url(current_partial.token, merge_refused=True)
        )
    return strategy.redirect(_choose_account_url(current_partial.token))


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
        raise LoginRefused(backend, _elevated_message(backend, elevated[0]))
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


def stop_if_removal_requested(strategy, backend, user=None, *args, **kwargs):
    """
    An account marked for removal can't be logged in to. The person is sent to
    the abort page instead, with the token -- being able to log in proves
    ownership as well as the email does. Nothing resumes: once aborted, they log
    in again.
    """
    if user is None or user.removal_requested is None:
        return
    # social_user may already have logged in an idproxy duplicate.
    request = strategy.request
    if request.user.is_authenticated and request.user.pk == user.pk:
        logout(request)
    logger.info("Login stopped for user %s: removal requested", user.pk)
    return strategy.redirect(abort_removal_path(user))


def create_user(strategy, details, backend, uid, user=None, *args, **kwargs):
    if user:
        return {"is_new": False}
    # None means the provider didn't say, so the model default applies
    fields = {
        name: value
        for name in backend.setting("USER_FIELDS", ["username", "email"])
        if (value := kwargs.get(name, details.get(name))) is not None
    }
    if not fields:
        return
    organisation = backend.organisation
    if backend.name == IDPROXY_PROVIDER:
        # identity_id is an id proxy identifier. An account created by any other
        # provider simply has none, and is reached through its UserSocialAuth.
        fields["identity_id"] = uid
    # Here rather than in ensure_userid, which would save the user a second time
    from voteit.core.utils import generate_valid_userid

    unsaved = User(
        organisation=organisation,
        first_name=fields.get("first_name", ""),
        last_name=fields.get("last_name", ""),
    )
    if userid := generate_valid_userid(unsaved):
        fields["userid"] = userid
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
    Pause the login until the user has accepted every terms of service
    version in effect.

    Before ``create_user``, so nobody gets an account without accepting. The
    client resumes with ``accept_tos=<version>``, the ``version`` from
    ``/api/terms-of-service/current/``, and the accept is stored by
    ``store_tos_accept`` once there is a user.
    """
    current = get_current_tos(backend.organisation, user)
    if not current.must_accept:
        return
    # Only the version they were shown counts, a newer one means asking again
    try:
        shown = parse_datetime(strategy.request_data().get(ACCEPT_TOS_FIELD) or "")
    except ValueError:
        shown = None
    if shown and is_aware(shown) and shown >= current.version:
        return {"accepted_tos": True}
    base = getattr(settings, "ACCEPT_TOS_URL", "/accept-tos")
    query = urlencode(
        {
            "partial_token": current_partial.token,
            "resume_url": f"/complete/{backend.name}/",
        }
    )
    return strategy.redirect(f"{base}?{query}")


def store_tos_accept(user=None, accepted_tos=False, *args, **kwargs):
    """
    Store what ``require_tos_accept`` got, now that there's a user.
    """
    if user is not None and accepted_tos:
        accept_tos(user)
