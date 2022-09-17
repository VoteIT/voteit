from __future__ import annotations
from typing import TYPE_CHECKING

from voteit.core.component import Registry

if TYPE_CHECKING:
    from voteit.components.abcs import ComponentAdapter


def get_meeting_component_adapters() -> Registry[str, ComponentAdapter]:
    from voteit.components.registries import meeting_components

    return meeting_components


def get_organisation_component_adapters() -> Registry[str, ComponentAdapter]:
    from voteit.components.registries import organisation_components

    return organisation_components
