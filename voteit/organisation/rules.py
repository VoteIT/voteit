import rules
from django.contrib.auth.models import User

from voteit.organisation.models import Organisation


@rules.predicate
def is_manager(user: User, organisation: Organisation):
    return organisation.managers.filter(pk=user.pk).exists()


@rules.predicate
def is_meeting_creator(user: User, organisation: Organisation):
    return organisation.meeting_creators.filter(pk=user.pk).exists()
