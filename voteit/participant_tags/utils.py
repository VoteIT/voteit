from voteit.components.registries import meeting_components
from voteit.core.workflows import EnabledWf
from voteit.meeting.models import Meeting
from voteit.participant_tags.components import NamespacedTags


def get_nst_class_from_ns(ns: str) -> type[NamespacedTags] | None:
    for adapter in meeting_components.values():
        if issubclass(adapter, NamespacedTags) and adapter.namespace == ns:
            return adapter


def get_adapted_from_ns(meeting: Meeting, ns: str) -> NamespacedTags | None:
    # Get in a saner way later on
    if adapter := get_nst_class_from_ns(ns):
        component = meeting.components.get(
            component_name=adapter.name, state=EnabledWf.ON
        )
        if component.is_valid:
            return component.adapted
