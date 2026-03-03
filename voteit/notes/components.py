from voteit.components.abcs import ComponentAdapter
from voteit.components.registries import meeting_components

__all__ = ("NotesComponent",)


@meeting_components
class NotesComponent(ComponentAdapter):
    name = "notes"
    title = "Notes"  # naming?
