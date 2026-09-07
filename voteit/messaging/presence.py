"""Who is online right now, counted.

Extracted from the "Online now" admin page so a management command can report
the same numbers rather than a second implementation that quietly drifts. The
admin adds its own links on top; nothing here knows about admin URLs.

Every count means "open *and* active recently" -- see ``Connection.online()``.
Channels never reports a consumer that died with its process, so an open row on
its own is not evidence of presence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.db import models

from voteit.messaging.models import Connection
from voteit.organisation.models import Organisation

if TYPE_CHECKING:
    from voteit.messaging.models import ConnectionQuerySet


@dataclass(frozen=True)
class OrganisationPresence:
    organisation: Organisation
    users: int
    sockets: int


@dataclass(frozen=True)
class Presence:
    """Totals plus the per-organisation breakdown, busiest first."""

    window: timedelta
    users: int
    sockets: int
    organisations: list[OrganisationPresence]

    @property
    def sockets_per_user(self) -> float:
        return round(self.sockets / self.users, 2) if self.users else 0

    @property
    def users_without_organisation(self) -> int:
        """Users online whose organisation is null.

        The FK is nullable only to ease testing, so this should be 0 in
        production -- but if it is not, the per-organisation rows do not add up
        to the total and saying so beats leaving someone to wonder.
        """
        return self.users - sum(row.users for row in self.organisations)


def online_per_organisation(online: ConnectionQuerySet) -> list[OrganisationPresence]:
    """Group open sockets by org -- via User, since Connection has no FK."""
    User = get_user_model()
    counts = list(
        User.objects.filter(pk__in=online.user_ids(), organisation__isnull=False)
        .values("organisation")
        .annotate(users=models.Count("pk", distinct=True))
        .order_by("-users")
    )
    sockets_by_org = _sockets_per_organisation(online)
    orgs_by_id = Organisation.objects.in_bulk([row["organisation"] for row in counts])
    rows = []
    for row in counts:
        if org := orgs_by_id.get(row["organisation"]):
            rows.append(
                OrganisationPresence(
                    organisation=org,
                    users=row["users"],
                    sockets=sockets_by_org.get(org.pk, 0),
                )
            )
    return rows


def _sockets_per_organisation(online: ConnectionQuerySet) -> dict[int, int]:
    """Sockets, not users: one person with four tabs is four of these."""
    User = get_user_model()
    org_by_user = dict(
        User.objects.filter(
            pk__in=online.user_ids(), organisation__isnull=False
        ).values_list("pk", "organisation")
    )
    counts: dict[int, int] = {}
    for user_id in online.values_list("user_id", flat=True):
        if org_id := org_by_user.get(user_id):
            counts[org_id] = counts.get(org_id, 0) + 1
    return counts


def presence(window: timedelta) -> Presence:
    online = Connection.objects.online(window)
    return Presence(
        window=window,
        users=online.values("user_id").distinct().count(),
        sockets=online.count(),
        organisations=online_per_organisation(online),
    )
