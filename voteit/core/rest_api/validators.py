from typing import TYPE_CHECKING

from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from voteit.agenda.models import AgendaItem
from voteit.core.rest_api.serializers import BaseModelSerializer
from voteit.meeting.permissions import MeetingPermissions

if TYPE_CHECKING:
    from voteit.meeting.models import MeetingGroup


class ValidateGroupAIContext:
    """
    Check that request user is a member of the group, or a moderator
    Make sure the group is part of this meeting.
    Also checks as_group combinations.
    This is for a ForeignKey field and only on a create operation!
    """

    requires_context = True

    def __init__(self, group_fieldname="meeting_group", as_group_fieldname="as_group"):
        self.group_fieldname = group_fieldname
        self.as_group_fieldname = as_group_fieldname

    def __call__(self, value, serializer: BaseModelSerializer):
        """
        Note the requirement on VoteITs BaseModelSerializer - it checks meeting groups so we don't need to do that.
        """
        if self.group_fieldname in value:
            assert isinstance(serializer, BaseModelSerializer)
            user = serializer.get_request_user()
            if user is None or user.is_anonymous:  # pragma: no cover
                # This should never really happen since create will always require authenticated users
                raise AuthenticationFailed()
            group: MeetingGroup = value[self.group_fieldname]
            if group is not None:
                # AI needed for both tests
                agenda_item = value["agenda_item"]
                assert isinstance(agenda_item, AgendaItem)
                # Check group in meeting
                if agenda_item.meeting is None:  # pragma: no cover
                    # Unattached agenda items aren't allowed right now, but keep this regardless
                    raise serializers.ValidationError(
                        {
                            self.group_fieldname: "Agenda item isn't attached to a meeting"
                        }
                    )
                # Moderator? Abort the rest of the check in that case
                if user.has_perm(MeetingPermissions.MODERATE, agenda_item.meeting):
                    return
                # This op doesn't require a DB lookup so do it before group check
                if value.get("as_group") and not group.post_as:
                    raise serializers.ValidationError(
                        {
                            self.as_group_fieldname: _(
                                "This meeting group doesn't allow you to create posts in its name. "
                                "(post_as=False)"
                            )
                        }
                    )
                # Group membership check should be done via BaseModelSerializer
