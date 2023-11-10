from __future__ import annotations
from rest_framework.serializers import ModelSerializer
from rest_framework.exceptions import ValidationError
from typing import TYPE_CHECKING

from voteit.core.abcs import MeetingContext
from voteit.meeting.models import Meeting
from voteit.proposal.models import Proposal

if TYPE_CHECKING:
    from voteit.core.models import User as UserType


def _get_meeting(value: dict, serializer: ModelSerializer) -> Meeting | None:
    """
    Fetch meeting from values + model serializer that works with a meeting context
    """
    if isinstance(serializer.instance, MeetingContext):
        return serializer.instance.meeting
    # Never used?
    # elif isinstance(value.get("meeting"), int):
    #    prop_qs = Proposal.objects.filter(agenda_item__meeting_id=value["meeting"])
    elif isinstance(value.get("meeting"), Meeting):
        return value.get("meeting")


class HighlightedValidator:
    requires_context = True

    def __init__(self, highlight_fieldname: str = "highlighted"):
        self.highlight_fieldname = highlight_fieldname

    def __call__(self, value: dict, serializer: ModelSerializer):
        highlighted = value.get(self.highlight_fieldname, None)
        if not highlighted:
            return
        meeting = _get_meeting(value, serializer)
        if meeting is None:
            raise ValidationError(
                {
                    self.highlight_fieldname: "Meeting or instance doesn't exist to check against."
                }
            )
        prop_pks = set(
            Proposal.objects.filter(agenda_item__meeting=meeting).values_list(
                "pk", flat=True
            )
        )
        if missing := set(highlighted) - prop_pks:
            raise ValidationError(
                {
                    self.highlight_fieldname: [
                        "The following proposals don't exist withing this "
                        f"meeting: %s" % ", ".join(str(x) for x in missing)
                    ]
                }
            )
