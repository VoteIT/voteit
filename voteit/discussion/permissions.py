from voteit.core.registries import permissions


class DiscussionPermissions:
    ADD = permissions.create("discussion.add_discussionpost", "agenda.AgendaItem")
    CHANGE = permissions.create(
        "discussion.change_discussionpost", "discussion.DiscussionPost"
    )
    DELETE = permissions.create(
        "discussion.delete_discussionpost", "discussion.DiscussionPost"
    )
    VIEW = permissions.create("discussion.view_discussionpost", "discussion.DiscussionPost")
