from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voteit.core.component import Registry


def get_poll_method_registry() -> Registry:
    from .registries import poll_methods

    return poll_methods


def get_electoral_policy_registry() -> Registry:
    from .registries import er_policy

    return er_policy
