from voteit.core.registries import permissions


class PresenceSystemPermissions:
    """
    The permissions must map the object permissions in django.

    >>> from voteit.core.testing import find_bad_permission_names
    >>> from voteit.presence.models import PresenceSystem
    >>> find_bad_permission_names(PresenceSystemPermissions, PresenceSystem)

    """

    ADD = permissions.create("presence.add_presencesystem", "meeting.Meeting")
    CHANGE = permissions.create(
        "presence.change_presencesystem", "presence.PresenceSystem"
    )
    DELETE = permissions.create(
        "presence.delete_presencesystem", "presence.PresenceSystem"
    )
    VIEW = permissions.create("presence.view_presencesystem", "presence.PresenceSystem")


class PresenceCheckPermissions:
    """
    The permissions must map the object permissions in django.

    >>> from voteit.core.testing import find_bad_permission_names
    >>> from voteit.presence.models import PresenceCheck
    >>> find_bad_permission_names(PresenceCheckPermissions, PresenceCheck)

    """

    ADD = permissions.create("presence.add_presencecheck", "presence.PresenceSystem")
    CHANGE = permissions.create(
        "presence.change_presencecheck", "presence.PresenceCheck"
    )
    DELETE = permissions.create(
        "presence.delete_presencecheck", "presence.PresenceCheck"
    )
    VIEW = permissions.create("presence.view_presencecheck", "presence.PresenceCheck")


class PresencePermissions:
    """
    The permissions must map the object permissions in django.

    >>> from voteit.core.testing import find_bad_permission_names
    >>> from voteit.presence.models import Presence
    >>> find_bad_permission_names(PresencePermissions, Presence)

    """

    # Change doesn't exist
    ADD = permissions.create("presence.add_presence", "presence.PresenceCheck")
    DELETE = permissions.create("presence.delete_presence", "presence.Presence")
    VIEW = permissions.create("presence.view_presence", "presence.Presence")
