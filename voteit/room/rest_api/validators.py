from rest_framework.serializers import ModelSerializer
from rest_framework.exceptions import ValidationError

from voteit.core.abcs import MeetingContext
from voteit.meeting.models import Meeting
from voteit.proposal.models import Proposal


class HighlightedValidator:
    requires_context = True

    def __init__(self, highlight_fieldname: str = "highlighted"):
        self.highlight_fieldname = highlight_fieldname

    def __call__(self, value: dict, serializer: ModelSerializer):
        highlighted = value.get(self.highlight_fieldname, None)
        if not highlighted:
            return
        if isinstance(serializer.instance, MeetingContext):
            prop_qs = Proposal.objects.filter(
                agenda_item__meeting=serializer.instance.meeting
            )
        # Never used?
        # elif isinstance(value.get("meeting"), int):
        #    prop_qs = Proposal.objects.filter(agenda_item__meeting_id=value["meeting"])
        elif isinstance(value.get("meeting"), Meeting):
            prop_qs = Proposal.objects.filter(agenda_item__meeting=value["meeting"])
        else:
            raise ValidationError(
                {
                    self.highlight_fieldname: "Meeting or instance doesn't exist to check against."
                }
            )
        prop_pks = set(prop_qs.values_list("pk", flat=True))
        if missing := set(highlighted) - prop_pks:
            raise ValidationError(
                {
                    self.highlight_fieldname: [
                        "The following proposals don't exist withing this "
                        f"meeting: %s" % ", ".join(str(x) for x in missing)
                    ]
                }
            )
