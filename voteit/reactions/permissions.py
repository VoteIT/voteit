from voteit.core.registries import permissions


class ReactionButtonPermissions:
    ADD = permissions.create("reactions.add_button", "meeting.Meeting")
    CHANGE = permissions.create("reactions.change_button", "reactions.ReactionButton")
    DELETE = permissions.create("reactions.delete_button", "reactions.ReactionButton")
    VIEW = permissions.create("reactions.view_button", "reactions.ReactionButton")
    # List who's reacted on this
    LIST_REACTIONS = permissions.create(
        "reactions.list_reactions", "reactions.ReactionButton"
    )
    # Add or remove a Reaction object
    CHANGE_REACTION = permissions.create(
        "reactions.change_reaction", "reactions.ReactionButton"
    )
