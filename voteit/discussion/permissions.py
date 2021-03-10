from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class DiscussionPermissions(ModelPermissions):
    model = "discussion_post"

    ADD = P("discussion.add_discussionpost", context="agenda_item")
    CHANGE = P("discussion.change_discussionpost")
    DELETE = P("discussion.delete_discussionpost")
    VIEW = P("discussion.view_discussionpost")
