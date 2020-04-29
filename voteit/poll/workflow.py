from django.utils.translation import gettext as _

from voteit.core.workflow import Workflow, workflows
from voteit.poll.security import CHANGE_POLL_STATE


@workflows
class PollWorkflow(Workflow):
    name = "poll_wf"
    PRIVATE = "private"
    UPCOMING = "upcoming"
    ONGOING = "ongoing"
    CLOSED = "closed"
    CANCELED = "canceled"

    initial_state = PRIVATE

    transitions = {}
    states = {
        PRIVATE: _("Private"),
        UPCOMING: _("Upcoming"),
        ONGOING: _("Ongoing"),
        CLOSED: _("Closed"),
        CANCELED: _("Canceled"),
    }


PollWorkflow.add_transitions(
    from_states=PollWorkflow.PRIVATE,
    to_states=PollWorkflow.UPCOMING,
    permission=CHANGE_POLL_STATE,
)


PollWorkflow.add_transitions(
    from_states=PollWorkflow.UPCOMING,
    to_states=[PollWorkflow.PRIVATE, PollWorkflow.ONGOING],
    permission=CHANGE_POLL_STATE,
)


PollWorkflow.add_transitions(
    from_states=PollWorkflow.ONGOING,
    to_states=[PollWorkflow.CANCELED, PollWorkflow.CLOSED],
    permission=CHANGE_POLL_STATE,
)
