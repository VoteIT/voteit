import rules
from django.contrib.auth.models import User

from voteit.organisation.models import Organisation


@rules.predicate
def is_manager(user: User, organisation: Organisation):
    return user in organisation.managers.all()


@rules.predicate
def is_meeting_creator(user: User, organisation: Organisation):
    return user in organisation.meeting_creators.all()
