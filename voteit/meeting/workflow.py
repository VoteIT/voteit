from django.utils.translation import gettext as _

from voteit.core.workflow import Workflow, workflows, ALL_STATES

_FIXME = "Fixme permission..."


@workflows
class MeetingWorkflow(Workflow):
    name = "meeting_wf"
    PRIVATE = "private"
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    CLOSED = "closed"
    ARCHIVED = "archived"

    initial_state = PRIVATE

    transitions = {}
    states = {
        PRIVATE: _("Private"),
        UPCOMING: _("Upcoming"),
        ONGOING: _("Ongoing"),
        CLOSED: _("Closed"),
        ARCHIVED: _("Archived"),
    }


MeetingWorkflow.add_transitions(
    from_states=ALL_STATES,
    to_states=ALL_STATES,
    permission=_FIXME,
)
