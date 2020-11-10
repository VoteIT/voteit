import rules
from django.contrib.auth.models import AbstractUser
from voteit.agenda.models import AgendaItem
from voteit.agenda.rules import is_non_private_ai
from voteit.core.rules import is_author, is_not_archived
from voteit.discussion.models import DiscussionPost
from voteit.meeting.rules import (
    is_moderator,
    is_discusser,
    is_participant,
    is_public,
)
from voteit.discussion.permissions import DiscussionPermissions


def is_not_discussion_blocked(user: AbstractUser, agenda_item: AgendaItem):
    return isinstance(agenda_item, AgendaItem) and not agenda_item.block_discussion


def can_add_discussion_post(user: AbstractUser, agenda_item: AgendaItem):
    """ Moderators can always add"""
    if isinstance(agenda_item, AgendaItem) and is_not_archived(
        user, agenda_item
    ):
        return is_moderator(user, agenda_item.meeting) or (
            is_non_private_ai(user, agenda_item)
            and is_not_discussion_blocked(user, agenda_item)
            and is_discusser(user, agenda_item.meeting)
        )


def can_view_discussion_post(user: AbstractUser, discussion_post: DiscussionPost):
    """ Currently discussions can't exist outside of agenda items and meeting. That might change.
    """
    try:
        meeting = discussion_post.agenda_item.meeting  # Will catch None too
    except AttributeError:  # pragma: no cover
        return
    return (
        is_moderator(user, meeting)
        or is_non_private_ai(user, discussion_post.agenda_item)
        and (is_participant(user, meeting) or is_public(user, meeting))
    )


def can_change_discussion_post(user: AbstractUser, discussion_post: DiscussionPost):
    """ Users have traditionally not been able to change their posts in voteit. This should perhaps change.
    """
    # FIXME: Do we want versioning and allow changes here?
    try:
        meeting = discussion_post.agenda_item.meeting  # Will catch None too
    except AttributeError:  # pragma: no coverage
        return
    return is_not_archived(user, meeting) and is_moderator(user, meeting)


def can_delete_discussion_post(user: AbstractUser, discussion_post: DiscussionPost):
    try:
        meeting = discussion_post.agenda_item.meeting  # Will catch None too
    except AttributeError:  # pragma: no coverage
        return
    if is_not_archived(user, meeting):
        return is_moderator(user, meeting) or is_author(user, discussion_post)


rules.add_perm(DiscussionPermissions.ADD, can_add_discussion_post)
rules.add_perm(DiscussionPermissions.VIEW, can_view_discussion_post)
rules.add_perm(DiscussionPermissions.CHANGE, can_change_discussion_post)
rules.add_perm(DiscussionPermissions.DELETE, can_delete_discussion_post)
