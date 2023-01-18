from voteit.active.components import ActiveUsersComponent
from voteit.core.workflows import EnabledWf
from voteit.meeting.models import Meeting


def active_enabled_for_meeting(meeting: Meeting) -> bool:
    return meeting.components.filter(
        component_name=ActiveUsersComponent.name, state=EnabledWf.ON
    ).exists()
