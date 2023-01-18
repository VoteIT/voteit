from voteit.components.abcs import ComponentAdapter
from voteit.components.registries import meeting_components

__all__ = ("ActiveUsersComponent",)


@meeting_components
class ActiveUsersComponent(ComponentAdapter):
    name = "active_users"
    title = "Active users"  # naming?
