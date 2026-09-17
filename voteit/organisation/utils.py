from __future__ import annotations

from collections import defaultdict
from typing import Generator
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from social_core.backends.base import BaseAuth
from social_core.backends.utils import load_backends
from social_django.models import UserSocialAuth
from social_django.utils import load_strategy

from voteit.organisation import IDPROXY_PROVIDER

if TYPE_CHECKING:
    from voteit.core.models import User


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


def get_user_identity_data(user: User) -> dict[str, set[str]]:
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
    """
    if user.is_anonymous:
        return {}
    backends = get_enabled_backends()
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
