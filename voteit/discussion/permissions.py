from voteit.core.permission import ModelPermissions
from voteit.core.permission import Permission as P


class DiscussionPermissions(ModelPermissions):
    model = "discussion_post"

    ADD = P("discussion.add_discussionpost", context="agenda_item")
    CHANGE = P("discussion.change_discussionpost")
    DELETE = P("discussion.delete_discussionpost")
    VIEW = P("discussion.view_discussionpost")
