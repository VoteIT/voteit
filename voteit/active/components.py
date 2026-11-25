from voteit.components.abcs import ComponentAdapter
from voteit.components.registries import meeting_components

__all__ = ("ActiveUsersComponent",)


@meeting_components
class ActiveUsersComponent(ComponentAdapter):
    name = "active_users"
    title = "Active users"  # naming?
    disable_on_close = True
    # Otherwise users entering an upcoming meeting are marked as active
    enable_on_start_when_required = True
