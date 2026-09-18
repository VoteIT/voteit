"""
Deciding whether a login belongs to an account that already exists.

Holding the address is the standard of proof. What the name decides is not
*whether* an account can be claimed but whether anyone has to be asked: an exact
match on both is taken silently, and everything else on the same address is put
to the person, with the account described, to recognise or decline.

The names really do differ, routinely -- someone with two surnames may have
given only one of them, or both -- so refusing those outright would strand the
most common case there is. Addresses get shared too, by spouses and by whoever
reads info@someorg.org, and those people decline. Every link is announced by
mail to the address the account already had, and can be undone.

Nothing here decides anything. The pipeline step does that, and the reporting
command measures it; both ask these same questions so the two cannot drift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models.functions import Lower
from django.db.models.functions import Trim

if TYPE_CHECKING:
    from voteit.core.models import User
    from voteit.organisation.models import Organisation


def normalise(value: str | None) -> str:
    """
    Compare people the way people write their names: case and stray spaces are
    not differences. Legacy rows are full of both.
    """
    return (value or "").strip().casefold()


def match_key(email: str | None, first_name: str | None, last_name: str | None):
    """
    The triple a match is made on, or ``None`` when any part is missing.

    A user with no email, or only half a name, can never be matched: there is
    not enough to tell them from anyone else.
    """
    key = (normalise(email), normalise(first_name), normalise(last_name))
    return key if all(key) else None


def user_match_key(user: User):
    return match_key(user.email, user.first_name, user.last_name)


def find_candidates(
    organisation: Organisation, *, provider: str, email: str | None
) -> list[User]:
    """
    Active accounts in this organisation reachable at this address.

    Anyone already holding a credential for ``provider`` is out: they have their
    own way in with it, so this login is somebody else.

    The address is trimmed and lowered in SQL, because legacy rows carry both.
    """
    wanted = normalise(email)
    if not wanted:
        return []
    return list(
        organisation.users.filter(is_active=True)
        .annotate(_match_email=Lower(Trim("email")))
        .filter(_match_email=wanted)
        .exclude(social_auth__provider=provider)
    )


def names_match(user: User, first_name: str | None, last_name: str | None) -> bool:
    """
    Whether this account carries the name the login arrived with.

    Only ever the difference between taking an account silently and asking about
    it. A name that does not match is a reason to ask, never a reason to refuse.
    """
    first, last = normalise(first_name), normalise(last_name)
    if not (first and last):
        return False
    return normalise(user.first_name) == first and normalise(user.last_name) == last


def is_elevated(user: User) -> bool:
    """
    Accounts an automatic link must never touch.

    The same ones ``HandleIdentitiesViewSet.get_prepped_qs`` already refuses to
    act on. Handing one of these to the wrong person is the worst thing this
    system can do, and there are few enough of them to ask about every time.
    """
    return bool(user.is_staff or user.is_superuser or user.organisation_roles.exists())
