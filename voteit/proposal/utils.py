from __future__ import annotations
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from voteit.core.component import Registry


def get_proposal_id_registry() -> Registry:
    from voteit.proposal.registries import proposal_id_registry

    return proposal_id_registry
