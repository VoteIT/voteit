from voteit.components.abcs import ComponentAdapter
from voteit.components.registries import meeting_components

__all__ = ("PresenceCheckComponent",)


@meeting_components
class PresenceCheckComponent(ComponentAdapter):
    name = "presence_check"
    title = "Presence heck"
