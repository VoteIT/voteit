from rest_framework import serializers
from voteit.agenda.models import AgendaItem
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.meeting.permissions import MeetingPermissions


class ValidateGroupAIContext:
    """
    Check that request user is a member of the group, or a moderator
    Make sure the group is part of this meeting
    This is for a ForeignKey field and only on a create operation!
    """

    requires_context = True

    def __init__(self, group_fieldname="meeting_group"):
        self.group_fieldname = group_fieldname

    def __call__(self, value, serializer: BaseModelSerializer):
        if self.group_fieldname in value:
            assert isinstance(serializer, BaseModelSerializer)
            user = serializer.get_request_user()
            group = value[self.group_fieldname]
            if group is not None:
                # AI needed for both tests
                agenda_item = value["agenda_item"]
                if isinstance(agenda_item, int):
                    agenda_item = AgendaItem.objects.get(pk=agenda_item)
                # Check group in meeting
                if agenda_item.meeting is None:
                    raise serializers.ValidationError(
                        {
                            self.group_fieldname: "Agenda item isn't attached to a meeting"
                        }
                    )
                if agenda_item.meeting != group.meeting:
                    raise serializers.ValidationError(
                        {
                            self.group_fieldname: f"MeetingGroup doesn't exist within this meeting"
                        }
                    )
                # Check group membership
                if not group.members.filter(pk=user.pk).exists():
                    if not user.has_perm(
                        MeetingPermissions.MODERATE, agenda_item.meeting
                    ):
                        raise serializers.ValidationError(
                            {
                                self.group_fieldname: f"User {user.pk} is not in group {group.pk} or moderator"
                            }
                        )
