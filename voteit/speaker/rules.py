import rules
from django.contrib.auth.models import User
from voteit.meeting.models import Meeting
from voteit.speaker.models import ListHandler


@rules.predicate
def is_list_moderator(user: User, list_handler: ListHandler) -> bool:
    return (
        isinstance(list_handler, ListHandler)
        and list_handler.moderators.filter(pk=user.pk).exists()
    )


@rules.predicate
def is_list_moderator(user: User, list_handler: ListHandler) -> bool:
    return (
        isinstance(list_handler, ListHandler)
        and list_handler.moderators.filter(pk=user.pk).exists()
    )
