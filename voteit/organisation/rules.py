import rules
from django.contrib.auth.models import User
from voteit.meeting.permissions import MeetingPermissions

from voteit.organisation.models import Organisation


@rules.predicate
def is_manager(user: User, organisation: Organisation):
    return organisation.managers.filter(pk=user.pk).exists()


@rules.predicate
def is_meeting_creator(user: User, organisation: Organisation):
    return organisation.meeting_creators.filter(pk=user.pk).exists()


# Object permissions
@rules.predicate
def can_add_meeting(user: User, organisation: Organisation):
    """ Meetings are added from organisations, so the check is against an organisation. """
    if organisation is not None:
        return is_manager(user, organisation) or is_meeting_creator(user, organisation)


rules.add_perm(MeetingPermissions.ADD, can_add_meeting)
