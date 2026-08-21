from __future__ import annotations

from typing import TYPE_CHECKING

from voteit.core.messages.role_updates import RolesChanged
from voteit.core.utils import get_model_shortname
from voteit.messaging.collectors import AppStateCollector
from voteit.messaging.registry import app_state_collectors
from voteit.organisation.channels import OrganisationChannel

if TYPE_CHECKING:
    from voteit.messaging.state import AppState


@app_state_collectors
class OrganisationRoles(AppStateCollector):
    """The subscribing user's own roles in this organisation."""

    name = "organisation.roles"
    channels = (OrganisationChannel,)
    order = 10

    def collect(self, state: AppState) -> None:
        roles = self.context.get_roles(self.user)
        if roles:
            state.append(
                RolesChanged(
                    payload={
                        "roles": roles,
                        "pk": self.context.pk,
                        "model": get_model_shortname(self.context),
                        "user_pk": self.user.pk,
                    }
                )
            )
