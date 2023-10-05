from voteit.core.permissions import ModelPermissions
from voteit.core.permissions import Permission as P


class ReactionButtonPermissions(ModelPermissions):
    model = "reaction_button"
    ADD = P("reactions.add_reactionbutton", context="meeting")
    CHANGE = P("reactions.change_reactionbutton")
    DELETE = P("reactions.delete_reactionbutton")
    VIEW = P("reactions.view_reactionbutton")
    # List who's reacted on this
    LIST_REACTIONS = P("reactions.list_reactions")


class ReactionPermissions(ModelPermissions):
    model = "reaction"
    ADD = P("reactions.add_reaction", context="reaction_button")
    DELETE = P("reactions.delete_reaction", context={"reaction", "reaction_button"})
