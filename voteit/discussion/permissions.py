from voteit.core.registries import permissions


class DiscussionPermissions:
    """
    The permissions must map the object permissions in django.

    >>> from voteit.core.testing import find_bad_permission_names
    >>> from voteit.discussion.models import DiscussionPost
    >>> find_bad_permission_names(DiscussionPermissions, DiscussionPost)

    """

    ADD = permissions.create("discussion.add_discussionpost", "agenda.AgendaItem")
    CHANGE = permissions.create(
        "discussion.change_discussionpost", "discussion.DiscussionPost"
    )
    DELETE = permissions.create(
        "discussion.delete_discussionpost", "discussion.DiscussionPost"
    )
    VIEW = permissions.create(
        "discussion.view_discussionpost", "discussion.DiscussionPost"
    )
