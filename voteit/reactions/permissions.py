from voteit.core.registries import permissions


class ReactionButtonPermissions:
    """
    The permissions must map the object permissions in django.

    >>> from voteit.core.testing import find_bad_permission_names
    >>> from voteit.reactions.models import ReactionButton
    >>> find_bad_permission_names(ReactionButtonPermissions, ReactionButton)

    """

    ADD = permissions.create("reactions.add_reactionbutton", "meeting.Meeting")
    CHANGE = permissions.create(
        "reactions.change_reactionbutton", "reactions.ReactionButton"
    )
    DELETE = permissions.create(
        "reactions.delete_reactionbutton", "reactions.ReactionButton"
    )
    VIEW = permissions.create(
        "reactions.view_reactionbutton", "reactions.ReactionButton"
    )
    # List who's reacted on this
    LIST_REACTIONS = permissions.create(
        "reactions.list_reactions", "reactions.ReactionButton"
    )


class ReactionPermissions:
    """
    The permissions must map the object permissions in django.

    >>> from voteit.core.testing import find_bad_permission_names
    >>> from voteit.reactions.models import Reaction
    >>> find_bad_permission_names(ReactionPermissions, Reaction)

    """

    ADD = permissions.create("reactions.add_reaction", "reactions.ReactionButton")
    DELETE = permissions.create("reactions.delete_reaction", "reactions.Reaction")
