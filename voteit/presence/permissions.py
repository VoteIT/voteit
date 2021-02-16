from voteit.core.registries import permissions


class PresenceSystemPermissions:
    ADD = permissions.create("voteit.presence.add_presence_system", "meeting.Meeting")
    CHANGE = permissions.create(
        "voteit.presence.change_presence_system", "presence.PresenceSystem"
    )
    DELETE = permissions.create(
        "voteit.presence.delete_presence_system", "presence.PresenceSystem"
    )
    VIEW = permissions.create(
        "voteit.presence.view_presence_system", "presence.PresenceSystem"
    )


class PresenceCheckPermissions:
    ADD = permissions.create(
        "voteit.presence.add_presence_check", "presence.PresenceSystem"
    )
    CHANGE = permissions.create(
        "voteit.presence.change_presence_check", "presence.PresenceCheck"
    )
    DELETE = permissions.create(
        "voteit.presence.delete_presence_check", "presence.PresenceCheck"
    )
    VIEW = permissions.create(
        "voteit.presence.view_presence_check", "presence.PresenceCheck"
    )


class PresencePermissions:
    # Change doesn't exist
    ADD = permissions.create("voteit.presence.add_presence", "presence.PresenceCheck")
    DELETE = permissions.create("voteit.presence.delete_presence", "presence.Presence")
    VIEW = permissions.create("voteit.presence.view_presence", "presence.Presence")
