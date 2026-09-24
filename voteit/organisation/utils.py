from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection
from typing import Generator
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils.timezone import now
from social_core.backends.base import BaseAuth
from social_core.backends.utils import load_backends
from social_django.models import UserSocialAuth
from social_django.utils import load_strategy

from voteit.organisation import IDPROXY_PROVIDER
from voteit.organisation import LOGIN_PROVIDER_SESSION_KEY
from voteit.organisation.models import TermsOfService
from voteit.organisation.models import UserAccept

if TYPE_CHECKING:
    from voteit.core.models import User
    from voteit.organisation.models import Organisation


def get_psa_backends() -> Generator[BaseAuth, None, None]:
    """
    This returns dummy versions of backends.
    """
    strategy = load_strategy()
    backend_class_names = strategy.get_backends()
    for backend in load_backends(backend_class_names).values():
        yield backend()


def get_enabled_backends() -> dict[str, type[BaseAuth]]:
    """
    Backend classes by provider name, for whatever ``AUTHENTICATION_BACKENDS``
    currently holds. A deployment may leave any of them out.

    ``load_backends`` caches in a module global that ignores its argument once
    warm, which ``signals.reload_social_backends`` flushes under test overrides.
    """
    return load_backends(settings.AUTHENTICATION_BACKENDS)


def get_user_identity_data(
    user: User, providers: Collection[str] | None = None
) -> dict[str, set[str]]:
    """
    Everything the enabled providers vouch for about this person, merged into
    one ``{scope: {value, ...}}`` dict.

    This is what decides which invites a user matches and which email they may
    put on their profile, so it must only ever carry validated data -- each
    backend's :meth:`get_identity_data` is responsible for that.

    A person may hold several accounts and several credentials, for historic
    reasons and because ``identity_id`` groups duplicates rather than merging
    them (see ``UserView.alternate`` / ``switch``), so this follows the
    identity as well as the row.

    ``providers`` limits it to those backends.
    """
    if user.is_anonymous:
        return {}
    backends = get_enabled_backends()
    if providers is not None:
        backends = {k: v for k, v in backends.items() if k in providers}
    # An account with no identity_id must only ever see its own rows: matching
    # on a null identity would join it to every other unlinked user.
    query = models.Q(user=user)
    if user.identity_id:
        query |= models.Q(
            # identity_id is an id proxy identifier, so only the id proxy's own
            # rows may be found by it.
            provider=IDPROXY_PROVIDER,
            uid=user.identity_id,
        ) | models.Q(
            # The person's other id proxy accounts, whatever they hold.
            user__identity_id=user.identity_id
        )
    results = defaultdict(set)
    for social in (
        UserSocialAuth.objects.filter(provider__in=backends)
        .exclude(extra_data={})
        .filter(query)
    ):
        backend = backends[social.provider]
        for scope, values in backend.get_identity_data(social).items():
            results[scope].update(values)
    return dict(results)


def get_user_member_ids(user: User) -> set[str]:
    """
    Member ids vouched for by any enabled backend that has them, i.e. sets
    ``MEMBER_ID_KEY``.
    """
    keys = {
        name: backend.MEMBER_ID_KEY
        for name, backend in get_enabled_backends().items()
        if getattr(backend, "MEMBER_ID_KEY", None)
    }
    if not keys:
        return set()
    data = get_user_identity_data(user, providers=keys)
    return set().union(*(data.get(key, set()) for key in keys.values()))


def get_login_provider(request) -> str | None:
    """
    Which login method this session signed in with, if it is one we still offer.

    Recorded by ``signals.remember_login_provider``. A deployment can drop a
    backend, and a name nobody can log in with now is no use to the client
    either, so it reads as nothing rather than as a provider.
    """
    session = getattr(request, "session", None)
    if session is None:
        return None
    name = session.get(LOGIN_PROVIDER_SESSION_KEY)
    return name if name in get_enabled_backends() else None


def get_active_tos(organisation: Organisation) -> TermsOfService | None:
    """
    The latest terms of service that have taken effect.
    """
    return organisation.tos.filter(version__lte=now()).order_by("-version").first()


def get_tos_to_accept(user: User) -> TermsOfService | None:
    """
    The active terms of service, if the user hasn't accepted them.
    """
    if not user.organisation_id:
        return None
    tos = get_active_tos(user.organisation)
    if tos and not UserAccept.objects.filter(user=user, tos=tos).exists():
        return tos
    return None


def accept_tos(user: User, tos: TermsOfService) -> UserAccept:
    # One row per user, the latest accept replaces the previous
    obj, _ = UserAccept.objects.update_or_create(
        user=user, defaults={"tos": tos, "accepted": now()}
    )
    return obj
