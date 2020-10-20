

class PresenceSystemPermissions:
    ADD = "voteit.presence.add_presence_system"  # Checked against meeting
    CHANGE = "voteit.presence.change_presence_system"
    DELETE = "voteit.presence.delete_presence_system"
    VIEW = "voteit.presence.view_presence_system"


class PresenceCheckPermissions:
    ADD = "voteit.presence.add_presence_check"  # Checked against PresenceSystem
    CHANGE = "voteit.presence.change_presence_check"
    DELETE = "voteit.presence.delete_presence_check"
    VIEW = "voteit.presence.view_presence_check"


class PresencePermissions:
    # Change doesn't exist
    ADD = "voteit.presence.add_presence"  # Checked against PresenceCheck
    DELETE = "voteit.presence.delete_presence"
    VIEW = "voteit.presence.view_presence"
