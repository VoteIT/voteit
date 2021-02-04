from voteit.messaging.decorators import outgoing
from voteit.messaging.messages.base import BaseObjectChanged


@outgoing
class MeetingChanged(BaseObjectChanged):
    name = "meeting.changed"
